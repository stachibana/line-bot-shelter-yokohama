# -*- coding: utf-8 -*-
import sys
import os
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    PostbackEvent,
    FollowEvent,
    ButtonsTemplate,
    PostbackTemplateAction,
    TemplateSendMessage,
    TextMessage,
    LocationMessage,
    LocationSendMessage,
    TextSendMessage,
    StickerSendMessage,
    MessageImagemapAction,
    ImagemapArea,
    ImagemapSendMessage,
    BaseSize
)
from io import BytesIO, StringIO
from PIL import Image
import requests
import urllib.parse
import urllib.request
import numpy
import math
import json


app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET'))

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

json_file = open('./merge.json', 'r')
pins = json.load(json_file)['results']['Shelter']

@handler.add(FollowEvent)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        [
            TextSendMessage(text='位置情報を送るとその近くの緊急時地域防災拠点、避難所、給水所、帰宅困難者一時滞在施設を案内します。'),
            TextSendMessage(text='line://nv/location'),
        ]
    )

    richmenu_id = 'richmenu-17c016f4c83245095a192ce90d0545fc'
    url = 'https://api.line.me/v2/bot/user/{}/richmenu/{}'.format(event.source.user_id, richmenu_id)
    method = 'POST'
    headers = {'Authorization' : 'Bearer {}'.format(os.environ.get('CHANNEL_ACCESS_TOKEN')), 'Content-Length' : '0'}

    obj = {}
    json_data = json.dumps(obj).encode('utf-8')

    request = urllib.request.Request(url, data=json_data, method=method, headers=headers)
    urllib.request.urlopen(request)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if event.message.text.isdigit():
        line_bot_api.reply_message(
            event.reply_token,
            [
                LocationSendMessage(
                    title = pins[int(event.message.text)]['Name'],
                    address = pins[int(event.message.text)]['Address'],
                    latitude = pins[int(event.message.text)]['Location'].split(',')[0],
                    longitude = pins[int(event.message.text)]['Location'].split(',')[1]
                )
            ]
        )
    elif event.message.text not in ['緊急時地域防災拠点', '避難所', '給水所', '帰宅困難者一時滞在施設']:
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text='位置情報を送るとその近くの緊急時地域防災拠点、避難所、給水所、帰宅困難者一時滞在施設を案内します。'),
                TextSendMessage(text='line://nv/location'),
            ]
        )

@app.route("/imagemap/<path:url>/<size>")
def imagemap(url, size):
    map_image_url = urllib.parse.unquote(url)
    response = requests.get(map_image_url)
    img = Image.open(BytesIO(response.content))
    img_resize = img.resize((int(size), int(size)))
    byte_io = BytesIO()
    img_resize.save(byte_io, 'PNG')
    byte_io.seek(0)
    return send_file(byte_io, mimetype='image/png')

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    lat = event.message.latitude
    lon = event.message.longitude

    message = TemplateSendMessage(
        alt_text='Buttons template',
        template=ButtonsTemplate(
            text='何を調べますか？',
            actions=[
                PostbackTemplateAction(
                    label='緊急時地域防災拠点', text='緊急時地域防災拠点',
                    data='Bousai,{},{}'.format(lat,lon)
                ),
                PostbackTemplateAction(
                    label='避難所', text='避難所',
                    data='Tsunami,{},{}'.format(lat,lon)
                ),
                PostbackTemplateAction(
                    label='給水所', text='給水所',
                    data='Water,{},{}'.format(lat,lon)
                ),
                PostbackTemplateAction(
                    label='帰宅困難者一時滞在施設', text='帰宅困難者一時滞在施設',
                    data='Temporary,{},{}'.format(lat,lon)
                ),
            ]
        )
    )
    line_bot_api.reply_message(event.reply_token, message)


@handler.add(PostbackEvent)
def handle_postback(event):

    lat = float(event.postback.data.split(',')[1])
    lon = float(event.postback.data.split(',')[2])

    zoomlevel = 16
    imagesize = 1040

    map_image_url = 'https://maps.googleapis.com/maps/api/staticmap?center={},{}&zoom={}&size=520x520&scale=2&maptype=roadmap&key={}'.format(lat, lon, zoomlevel, os.environ.get('GOOGLE_API_KEY'));
    map_image_url += '&markers=color:{}|label:{}|{},{}'.format('blue', '', lat, lon)

    center_lat_pixel, center_lon_pixel = latlon_to_pixel(lat, lon)

    marker_color = 'red';
    label = 'E';
    pin_width = 60 * 1.5;
    pin_height = 84 * 1.5;

    actions = []
    for i, pin in enumerate(pins):
        if(pin['Type'] != event.postback.data.split(',')[0]):
            continue

        target_lat_pixel, target_lon_pixel = latlon_to_pixel(float(pin['Location'].split(',')[0]), float(pin['Location'].split(',')[1]))

        delta_lat_pixel  = (target_lat_pixel - center_lat_pixel) >> (21 - zoomlevel - 1);
        delta_lon_pixel  = (target_lon_pixel - center_lon_pixel) >> (21 - zoomlevel - 1);

        marker_lat_pixel = imagesize / 2 + delta_lat_pixel;
        marker_lon_pixel = imagesize / 2 + delta_lon_pixel;

        x = marker_lat_pixel
        y = marker_lon_pixel

        if(pin_width / 2 < x < imagesize - pin_width / 2 and pin_height < y < imagesize - pin_width):

            map_image_url += '&markers=color:{}|label:{}|{},{}'.format(marker_color, label, pin['Location'].split(',')[0], pin['Location'].split(',')[1])

            actions.append(MessageImagemapAction(
                text = str(i),
                area = ImagemapArea(
                    x = x - pin_width / 2,
                    y = y - pin_height / 2,
                    width = pin_width,
                    height = pin_height
                )
            ))
            if len(actions) > 9:
                break

    message = ImagemapSendMessage(
        base_url = 'https://{}/imagemap/{}'.format(request.host, urllib.parse.quote_plus(map_image_url)),
        alt_text = '地図',
        base_size = BaseSize(height=imagesize, width=imagesize),
        actions = actions
    )
    line_bot_api.reply_message(
        event.reply_token,
        [
            message
        ]
    )

offset = 268435456;
radius = offset / numpy.pi;

def latlon_to_pixel(lat, lon):
    lat_pixel = round(offset + radius * lon * numpy.pi / 180);
    lon_pixel = round(offset - radius * math.log((1 + math.sin(lat * numpy.pi / 180)) / (1 - math.sin(lat * numpy.pi / 180))) / 2);
    return lat_pixel, lon_pixel

if __name__ == "__main__":
    app.debug = True
    app.run()
