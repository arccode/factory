#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This script generates a PNG file according to the specified text message and attributes.

The attributes are saved as a text chunk in the PNG file. If we are
overwriting an existing PNG file and the attributes are the same as that used
to generate the existing PNG file, we just skip this file.
"""


import argparse
import cairo
import os
import pango
import pangocairo
import sys
import yaml
from PIL import Image, PngImagePlugin


def WriteAttrData(img_path, attr):
  i = Image.open(img_path)
  meta = PngImagePlugin.PngInfo()
  meta.add_text('text_attr', yaml.dump(attr).encode('UTF-8'))
  i.save(img_path, 'png', pnginfo=meta)


def GetAttrData(img_path):
  try:
    i = Image.open(img_path)
    return yaml.load(i.info['text_attr'].decode('UTF-8'))
  except:  # pylint: disable=W0702
    return None


def CheckDuplicate(attr, img_path):
  if not os.path.exists(img_path):
    return False
  return GetAttrData(img_path) == attr


def GetFont(attr):
  FONT = 'sans-serif, %dpx'
  return pango.FontDescription(FONT % attr['font_size'])


def ColorTriplet(color):
  if color[0] == '#':
    color = color[1:]
  assert len(color) == 6
  return (int(color[0:2], 16),
          int(color[2:4], 16),
          int(color[4:6], 16))


def FillInDefaultAttr(attr):
  attr.setdefault('bg_color', '#000000')
  attr.setdefault('fg_color', '#ffffff')
  attr.setdefault('font_size', 20)


def GetTextLayout(pangocontext, attr):
  layout = pangocontext.create_layout()
  font = GetFont(attr)
  layout.set_font_description(font)
  layout.set_text(attr['text'])
  return layout


def GetTextSize(attr):
  surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1000, 1000)
  pangocontext = pangocairo.CairoContext(cairo.Context(surface))
  return GetTextLayout(pangocontext, attr).get_pixel_size()


def CreateMessageImage(attr):
  FillInDefaultAttr(attr)
  img_path = attr['image']
  if CheckDuplicate(attr, img_path):
    sys.stdout.write('%s is up-to-date. Skipping.\n' % img_path)
    return

  w, h = GetTextSize(attr)

  surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
  context = cairo.Context(surface)

  context.rectangle(0, 0, w, h)
  context.set_source_rgb(*ColorTriplet(attr['bg_color']))
  context.fill()

  pangocontext = pangocairo.CairoContext(context)
  layout = GetTextLayout(pangocontext, attr)
  context.set_source_rgb(*ColorTriplet(attr['fg_color']))
  pangocontext.update_layout(layout)
  pangocontext.show_layout(layout)

  with open(img_path, 'w') as image_output:
    surface.write_to_png(image_output)
  WriteAttrData(img_path, attr)

  sys.stdout.write('Generated %s.\n' % img_path)


def main():
  parser = argparse.ArgumentParser(
      description='Make text image.')
  parser.add_argument('--input_file', '-i',
                      help='Yaml file with the following field:\n'
                      '  text - The text to draw\n'
                      '  font_size - The size of text\n'
                      '  fg_color - Foreground color\n'
                      '  bg_color - Background color\n'
                      'If an input file is specified, other arguments\n'
                      'are ignored.',
                      required=False)
  parser.add_argument('--output', '-o', help='Output image file name',
                      required=False)
  parser.add_argument('--text', '-t', help='Text to draw', required=False)
  parser.add_argument('--fg_color', '-f', help='Foreground color',
                      default='#ffffff', required=False)
  parser.add_argument('--bg_color', '-b', help='Background color',
                      default='#000000', required=False)
  parser.add_argument('--font_size', '-s', help='Font size in px',
                      type=int, default=20, required=False)
  args = parser.parse_args()

  if args.input_file:
    attrs = yaml.load(open(args.input_file, 'r').read())
  elif args.text and args.output:
    attrs = [{'image': args.output, 'text': args.text}]
    for k in ['fg_color', 'bg_color', 'font_size']:
      if args.__dict__[k]:
        attrs[0][k] = args.__dict__[k]
  else:
    sys.stderr.write(parser.format_usage())
    sys.exit(1)

  for attr in attrs:
    attr['text'] = attr['text'].replace('\\n', '\n')
    CreateMessageImage(attr)

if __name__ == '__main__':
  main()
