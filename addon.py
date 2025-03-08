import sys
import xbmcgui
import xbmcplugin
import xbmcaddon
import json
import http.client
import time
from urllib.parse import parse_qsl

try:
    import StorageServer
except:
    import storageserverdummy as StorageServer
cache = StorageServer.StorageServer("plugin.video.play.joj.sk", 1)

addon = xbmcaddon.Addon()

__url__ = sys.argv[0]
__handle__ = int(sys.argv[1])

screens = {
    "Domov": "screen-Lxye9UzYirbdU8gT6zIZ",
    "Seriály": "screen-6u1OuNZpEZJ5mvFAr_kwA",
    "Filmy": "screen-sDYvdxFDr6YuXBrJNq4Pf",
    "Šport": "screen-jNBx-DFZSx6PazsFvlPol",
    "Kino": "screen-Hu1-54YQnc69N4CTNRMcm",
    "Podcasty": "screen-Z9EMIUtQqNUU-C-f8lRVz",
    "Dokumenty": "screen-d_xouIReAph2uSRkR70eb",
    "Deti": "screen-vmptBEawEZaKP5VzokZeE"
}

def getToken(email, password):
    conn = http.client.HTTPSConnection("www.googleapis.com")

    payload = json.dumps({
        "email": email,
        "password": password,
        "returnSecureToken": True,
        "tenantId": "XEpbY0V54AE34rFO7dB2-i9m04"
    })

    headers = {"content-type": "application/json"}

    conn.request("POST", "/identitytoolkit/v3/relyingparty/verifyPassword?key=AIzaSyB02udgMkNLADkLJ_w5YNBMR2VR1WHfusI", payload, headers)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    if "error" in responseJson:
        xbmcgui.Dialog().ok("Error", responseJson["error"]["message"])
        return

    return responseJson.get("idToken")

token = cache.cacheFunction(getToken, addon.getSetting("email"), addon.getSetting("password"))

def firebaseQuery(path, query):
    conn = http.client.HTTPSConnection("firestore.googleapis.com")

    payload = json.dumps(query)

    headers = {
        "content-type": "application/json",
        "authorization": "Bearer " + token
    }

    conn.request("POST", "/v1/projects/tivio-production/databases/(default)/documents" + path + ":runQuery", payload, headers)

    res = conn.getresponse()
    data = res.read()

    return json.loads(data.decode("utf-8"))

def getItemsInSeason(id, season):
    query = {
        "structuredQuery": {
            "from": [
                {
                    "collectionId": "videos"
                }
            ],
            "where": {
                "compositeFilter": {
                    "op": "AND",
                    "filters": [
                        {
                            "fieldFilter": {
                                "field": {
                                    "fieldPath": "tags"
                                },
                                "op": "ARRAY_CONTAINS_ANY",
                                "value": {
                                    "arrayValue": {
                                        "values": [
                                            {
                                                "referenceValue": "projects/tivio-production/databases/(default)/documents/organizations/dEpbY0V54AE34rFO7dB2/tags/" + id
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        {
                            "fieldFilter": {
                                "field": {
                                    "fieldPath": "publishedStatus"
                                },
                                "op": "EQUAL",
                                "value": {
                                    "stringValue": "PUBLISHED"
                                }
                            }
                        },
                        {
                            "fieldFilter": {
                                "field": {
                                    "fieldPath": "transcodingStatus"
                                },
                                "op": "EQUAL",
                                "value": {
                                    "stringValue": "ENCODING_DONE"
                                }
                            }
                        },
                        {
                            "fieldFilter": {
                                "field": {
                                    "fieldPath": "seasonNumber"
                                },
                                "op": "EQUAL",
                                "value": {
                                    "integerValue": str(season)
                                }
                            }
                        }
                    ]
                }
            },
            "orderBy": [
                {
                    "field": {
                        "fieldPath": "episodeNumber"
                    },
                    "direction": "ASCENDING"
                },
                {
                    "field": {
                        "fieldPath": "__name__"
                    },
                    "direction": "ASCENDING"
                }
            ]
        }
    }

    return list(map(parseVideoFirebase, firebaseQuery("", query)))

def getItemsInScreen(id):
    conn = http.client.HTTPSConnection("europe-west3-tivio-production.cloudfunctions.net")

    payload = json.dumps({
        "data": {
            "organizationId": "dEpbY0V54AE34rFO7dB2",
            "screenId": id,
            "offset": 0,
            "limit": 100,
            "initialTilesCount": 10
        }
    })

    headers = {
        "content-type": "application/json",
        "authorization": "Bearer " + token
    }

    conn.request("POST", "/getRowsInScreen3", payload, headers)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    items = responseJson["result"]["items"]

    list = []

    for item in items:
        if(item["rowComponent"] == "BANNER"):
            list.append({
                "id": item["tiles"]["items"][0]["id"],
                "type": "video" if item["tiles"]["items"][0]["itemType"] == "VIDEO" else "series",
                "name": getFromLangs(item["tiles"]["items"][0]["name"]),
                "description": getFromLangs(item["tiles"]["items"][0]["itemSpecificData"].get("description")),
                "image": getImage(item["tiles"]["items"][0]["itemSpecificData"]["assets"]) if "assets" in item["tiles"]["items"][0]["itemSpecificData"] else "https://assets.tivio.studio/videos/" + item["tiles"]["items"][0]["id"] + "/cover"
            })
        elif(item["rowComponent"] == "ROW" and id != screens["Podcasty"]):
            name = getFromLangs(item["name"])

            if(name != "Live TV" and name != "Pokračovať v sledovaní"):
                list.append({
                    "id": item["path"].split("/")[-1],
                    "name": name,
                    "type": "category"
                })

    return list

def chunkify(arr, size):
    return [arr[i:i+size] for i in range(0, len(arr), size)]

def getItemsInCategory(id):
    conn = http.client.HTTPSConnection("firestore.googleapis.com")

    conn.request("GET", "/v1/projects/tivio-production/databases/(default)/documents/organizations/dEpbY0V54AE34rFO7dB2/rows/" + id)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    videosFirebaseList = []
    seriesFirebaseList = []

    for item in responseJson["fields"]["customItems"]["arrayValue"]["values"]:
        refVal = item["mapValue"]["fields"]["itemRef"]["referenceValue"]
        if "/videos/" in refVal:
            videosFirebaseList.append({"referenceValue": refVal})
        elif "/tags/" in refVal:
            seriesFirebaseList.append({"referenceValue": refVal})

    seriesData = []
    for chunk in chunkify(seriesFirebaseList, 30):
        seriesQuery = {
            "structuredQuery": {
                "from": [{"collectionId": "tags"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "__name__"},
                        "op": "IN",
                        "value": {"arrayValue": {"values": chunk}}
                    }
                },
                "orderBy": [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}]
            }
        }
        seriesData.extend(firebaseQuery("/organizations/dEpbY0V54AE34rFO7dB2", seriesQuery))

    videoData = []
    for chunk in chunkify(videosFirebaseList, 30):
        videoQuery = {
            "structuredQuery": {
                "from": [{"collectionId": "videos"}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "__name__"},
                                    "op": "IN",
                                    "value": {"arrayValue": {"values": chunk}}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "publishedStatus"},
                                    "op": "EQUAL",
                                    "value": {"stringValue": "PUBLISHED"}
                                }
                            }
                        ]
                    }
                },
                "orderBy": [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}]
            }
        }
        videoData.extend(firebaseQuery("", videoQuery))
    
    outList = []
    for item in responseJson["fields"]["customItems"]["arrayValue"]["values"]:
        refVal = item["mapValue"]["fields"]["itemRef"]["referenceValue"]
        itemId = refVal.split("/")[-1]
        if "/videos/" in refVal:
            video = next((x for x in videoData if x["document"]["name"] == refVal), None)
            
            if video is not None:
                outList.append(parseVideoFirebase(video))
        else:
            series = next((x for x in seriesData if x["document"]["name"] == refVal), None)
            
            if series is not None:
                outList.append({
                    "id": itemId,
                    "type": "series",
                    "name": getFromLangsFirebase(series["document"]["fields"].get("name")),
                    "description": getFromLangsFirebase(series["document"]["fields"].get("description")),
                    "image": getImageFirebase(series["document"]["fields"]["assets"]) if "assets" in series["document"]["fields"] else "https://assets.tivio.studio/videos/" + itemId + "/cover"
                })
    
    return outList

def getItemsInSeries(id):
    conn = http.client.HTTPSConnection("firestore.googleapis.com")

    conn.request("GET", "/v1/projects/tivio-production/databases/(default)/documents/organizations/dEpbY0V54AE34rFO7dB2/tags/" + id)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    list = []

    for item in responseJson["fields"]["metadata"]["arrayValue"]["values"]:
        if(item["mapValue"]["fields"]["key"]["stringValue"] == "availableSeasons"):
            for season in sorted(item["mapValue"]["fields"]["value"]["arrayValue"]["values"], key=lambda x: int(x["mapValue"]["fields"]["seasonNumber"]["integerValue"])):
                list.append({
                    "id": id,
                    "season": season["mapValue"]["fields"]["seasonNumber"]["integerValue"],
                    "name": "Séria " + season["mapValue"]["fields"]["seasonNumber"]["integerValue"],
                    "type": "season"
                })

    return list

def parseVideoFirebase(input):
    id = input["document"]["name"].split("/")[-1]
    return {
        "type": "video",
        "id": id,
        "name": getFromLangsFirebase(input["document"]["fields"].get("name")) if getFromLangsFirebase(input["document"]["fields"].get("name")) is not None else "Epizóda " + input["document"]["fields"]["episodeNumber"]["integerValue"] if "episodeNumber" in input["document"]["fields"] else "Epizóda",
        "description": getFromLangsFirebase(input["document"]["fields"].get("description")),
        "image": getImageFirebase(input["document"]["fields"]["assets"]) if "assets" in input["document"]["fields"] else "https://assets.tivio.studio/videos/" + id + "/cover"
    }

def getFromLangs(input):
    if isinstance(input, str) or input is None:
        return input

    return (
        input.get("sk") 
        if input.get("sk") is not None 
        else (input.get("cs") if input.get("cs") is not None else input.get("en"))
    )

def getFromLangsFirebase(input):
    if input is None:
        return None

    if "stringValue" in input:
        return input["stringValue"]

    if "mapValue" not in input:
        return None

    return (
        input["mapValue"]["fields"]["sk"]["stringValue"]
        if "sk" in input["mapValue"]["fields"]
        else (input["mapValue"]["fields"]["cs"]["stringValue"] if "cs" in input["mapValue"]["fields"] else input["mapValue"]["fields"]["en"]["stringValue"])
    )

imageKeys = ["video_detail", "tag_detail", "cover", "tag_landscape_cover", "banner", "banner_mobile", "portrait", "tag_banner", "tag_banner_mobile", "tag_portrait_cover", "background_banner_mobile"]

def getImage(assets):
    for key in imageKeys:
        if key in assets:
            tagData = assets[key]
            if "@1" in tagData and "background" in tagData["@1"]:
                return tagData["@1"]["background"]

def getImageFirebase(assets):
    if "mapValue" not in assets or "fields" not in assets["mapValue"]:
        return None
    for key in imageKeys:
        if key in assets["mapValue"]["fields"]:
            tagData = assets["mapValue"]["fields"][key]
            if "@1" in tagData["mapValue"]["fields"] and "background" in tagData["mapValue"]["fields"]["@1"]["mapValue"]["fields"]:
                return tagData["mapValue"]["fields"]["@1"]["mapValue"]["fields"]["background"]["stringValue"]

def search(query, type):
    conn = http.client.HTTPSConnection("ol4uz1qnhs-dsn.algolia.net")

    videoFilter = "organizationPath:organizations/dEpbY0V54AE34rFO7dB2 AND isDraft:false AND isDuplicate:false AND hide:false AND NOT contentType:SERIES"
    seriesFilter = "organizationPath:organizations/dEpbY0V54AE34rFO7dB2"

    videoPath = "/1/indexes/videos/query"
    seriesPath = "/1/indexes/tags/query"

    auth = "?x-algolia-api-key=NTdiZTE4MWI4NGYzYWU0ZGE1ZDVlNWVmZWM2MGFkYWE4NWI2ODNhMTVmMTkxMTg2YWIwMzQwNmQzYzEzMDE2MHJlc3RyaWN0SW5kaWNlcz0lNUIlMjJ2aWRlb3MlMjIlMkMlMjJ2aWRlb3NfY3JlYXRlZF9kZXNjJTIyJTJDJTIydGFncyUyMiUyQyUyMnR2Q2hhbm5lbHMlMjIlNUQ=&x-algolia-application-id=OL4UZ1QNHS"

    payload = json.dumps({
        "query": query,
        "filters": videoFilter if type == "video" else seriesFilter,
        "hitsPerPage": 5,
        "page": 0
    })

    headers = { "content-type": "application/json" }

    conn.request("POST", (videoPath if type == "video" else seriesPath) + auth, payload, headers)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    list = []

    for item in responseJson["hits"]:
        list.append({
            "id": item["objectID"],
            "type": "video" if type == "video" else "series",
            "name": getFromLangs(item.get("name")),
            "description": getFromLangs(item.get("description")),
            "image": getImage(item["assets"]) if "assets" in item else "https://assets.tivio.studio/videos/" + item["objectID"] + "/cover"
        })

    return list

def play(id, type):
    conn = http.client.HTTPSConnection("europe-west3-tivio-production.cloudfunctions.net")

    payload = json.dumps({
        "data": {
            "id": id,
            "documentType": type,
            "capabilities": [
                {
                    "codec": "h264",
                    "protocol": "dash",
                    "encryption": "none"
                }
            ]
        }
    })

    headers = {
        "content-type": "application/json",
        "authorization": "Bearer " + token
    }

    conn.request("POST", "/getSourceUrl", payload, headers)

    res = conn.getresponse()
    data = res.read()

    responseJson = json.loads(data.decode("utf-8"))

    if "error" in responseJson:
        xbmcgui.Dialog().ok("Error", responseJson["error"]["message"])
        return

    playItem = xbmcgui.ListItem(path=responseJson["result"]["url"], offscreen=True)

    playItem.setMimeType("application/dash+xml")
    playItem.setContentLookup(False)

    playItem.setProperty("inputstream", "inputstream.adaptive")
    playItem.setProperty("inputstream.adaptive.manifest_type", "mpd")

    xbmcplugin.setResolvedUrl(__handle__, True, listitem=playItem)

def renderList(list):
    added = []

    for item in list:
        if item["id"] not in added:
            if item["type"] == "video":
                li = xbmcgui.ListItem(item["name"])

                if "image" in item and item["image"] is not None:
                    li.setArt({"poster": item["image"]})

                info = {}
                if "name" in item and item["name"] is not None:
                    info["title"] = item["name"]
                if "description" in item and item["description"] is not None:
                    info["plot"] = item["description"]

                li.setInfo("video", info)

                li.setProperty("IsPlayable", "true")

                xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=play&id={1}&type=video".format(__url__, item["id"]), listitem=li, isFolder=False)
            elif item["type"] == "season":
                li = xbmcgui.ListItem(item["name"])

                li.setInfo("video", {
                    "title": item["name"]
                })

                xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=getItemsInSeason&id={1}&season={2}".format(__url__, item["id"], item["season"]), listitem=li, isFolder=True)
            elif item["type"] == "series":
                li = xbmcgui.ListItem(item["name"])

                if "image" in item and item["image"] is not None:
                    li.setArt({"poster": item["image"], "icon": "DefaultTVShows.png"})
                else:
                    li.setArt({"icon": "DefaultTVShows.png"})
                
                info = {}
                if "name" in item and item["name"] is not None:
                    info["title"] = item["name"]
                if "description" in item and item["description"] is not None:
                    info["plot"] = item["description"]
                
                li.setInfo("video", info)

                xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=getItemsInSeries&id={1}".format(__url__, item["id"]), listitem=li, isFolder=True)
            elif item["type"] == "category":
                li = xbmcgui.ListItem(item["name"])

                xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=getItemsInCategory&id={1}".format(__url__, item["id"]), listitem=li, isFolder=True)
            elif item["type"] == "channel":
                li = xbmcgui.ListItem(item["name"])

                li.setArt({"poster": item["preview"] + "?v=" + str(time.time()), "icon": item["logo"]})

                li.setProperty("IsPlayable", "true")

                xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=play&id={1}&type=tvChannel".format(__url__, item["id"]), listitem=li, isFolder=False)

            if "season" not in item:
                added.append(item["id"])
    xbmcplugin.endOfDirectory(__handle__)

def router(paramString):
    params = dict(parse_qsl(paramString[1:]))
    
    if params:
        if params["action"] == "getItemsInScreen":
            renderList(getItemsInScreen(params["id"]))
        elif params["action"] == "getItemsInCategory":
            renderList(getItemsInCategory(params["id"]))
        elif params["action"] == "getItemsInSeries":
            list = getItemsInSeries(params["id"])

            if len(list) == 1:
                renderList(getItemsInSeason(params["id"], list[0]["season"]))
            else:
                renderList(list)
        elif params["action"] == "getItemsInSeason":
            renderList(getItemsInSeason(params["id"], params["season"]))
        elif params["action"] == "play":
            play(params["id"], params["type"])
        elif params["action"] == "search":
            keyboard = xbmc.Keyboard()
            keyboard.doModal()
            input = None
            if (keyboard.isConfirmed()):
                input = keyboard.getText()
            
            if input is not None:
                list = search(input, "video") + search(input, "series")

                renderList(list)
        elif params["action"] == "listChannels":
            list = [
                {
                    "id": "LYyAwEjjqmj8kMY23Lqw",
                    "type": "channel",
                    "name": "JOJ",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/101/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/tvjoj.png"
                },
                {
                    "id": "60K9GwR6CLApIHVyNYOj",
                    "type": "channel",
                    "name": "JOJ Plus",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/102/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/jojplus.png"
                },
                {
                    "id": "0D9v2CuujVAlLJJTyLWd",
                    "type": "channel",
                    "name": "WAU",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/103/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/wautv.png"
                },
                {
                    "id": "7tl6We5FhLyCfZcmSG6F",
                    "type": "channel",
                    "name": "JOJ 24",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/111/categories/screenshot/1.jpg",
                    "logo": "https://i.ibb.co/fV5RJx6G/joj24.png"
                },
                {
                    "id": "OE8iUSCBeLn8CIb0mL57",
                    "type": "channel",
                    "name": "JOJ Šport",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/110/categories/screenshot/1.jpg",
                    "logo": "https://i.ibb.co/wFqgKVzN/jojsport.png"
                },
                {
                    "id": "XA7YXR0HIuS4HGVgSZli",
                    "type": "channel",
                    "name": "JOJ Šport 2",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/118/categories/screenshot/1.jpg",
                    "logo": "https://i.ibb.co/pr5mtbP2/jojsport2.png"
                },
                {
                    "id": "vSmKCe7UZp40PvCLXvtb",
                    "type": "channel",
                    "name": "JOJ Svet",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/114/categories/screenshot/1.jpg",
                    "logo": "https://i.ibb.co/wh64Gf8X/jojsvet.png"
                },
                {
                    "id": "oALPnvtbTB4yuM4cLpnF",
                    "type": "channel",
                    "name": "JOJko",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/104/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/jojko.png"
                },
                {
                    "id": "7oGizuVUXRJGckpoVGUB",
                    "type": "channel",
                    "name": "JOJ Cinema",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/105/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/jojcinema.png"
                },
                {
                    "id": "aYB0bZQo5X5BuuaXl43H",
                    "type": "channel",
                    "name": "CS Film",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/106/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/csfilm.png"
                },
                {
                    "id": "UY5IgHcFriJV4Dh54RCS",
                    "type": "channel",
                    "name": "CS History",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/107/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/cshistory.png"
                },
                {
                    "id": "cIM4bKpVNVziiCrs5LJk",
                    "type": "channel",
                    "name": "CS Mystery",
                    "preview": "https://cnt.iptv.joj.sk/contentserver/contents/108/categories/screenshot/1.jpg",
                    "logo": "https://raw.githubusercontent.com/MarhyCZ/picons/refs/heads/master/640/csmystery.png"
                }
            ]

            renderList(list)
    else:
        for screen in screens:
            li = xbmcgui.ListItem(screen)

            xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=getItemsInScreen&id={1}".format(__url__, screens[screen]), listitem=li, isFolder=True)
        
        tvLi = xbmcgui.ListItem("TV naživo")

        xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=listChannels".format(__url__, screens[screen]), listitem=tvLi, isFolder=True)

        searchLi = xbmcgui.ListItem("Vyhľadávanie")

        searchLi.setArt({"icon": "DefaultAddonsSearch.png"})

        xbmcplugin.addDirectoryItem(handle=__handle__, url="{0}?action=search".format(__url__), listitem=searchLi, isFolder=True)
        
        xbmcplugin.endOfDirectory(__handle__)

if __name__ == "__main__":
    router(sys.argv[2])