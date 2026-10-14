from PIL import Image, ImageDraw, ImageFont
import math

im = Image.open('assets/kic.png').convert("RGBA")
overlay = Image.new("RGBA", (1080, 1080), (0,0,0,0))
draw = ImageDraw.Draw(overlay)

# Draw Photo Slot
PHOTO_SLOT = (75, 360, 275, 390) 
draw.rectangle([PHOTO_SLOT[0], PHOTO_SLOT[1], PHOTO_SLOT[0]+PHOTO_SLOT[2], PHOTO_SLOT[1]+PHOTO_SLOT[3]], fill=(255,0,0,128))

# Draw text lines
VALUE_X = 510
START_Y = 485
LINE_STEP = 55
try:
    font = ImageFont.truetype("assets/Mukta/Mukta-Regular.ttf", 36)
except:
    font = ImageFont.load_default()

for i in range(5):
    draw.text((VALUE_X, START_Y + i*LINE_STEP), f"Test Line {i}", font=font, fill=(0,0,255,255))

draw.text((810, 680), "Footer Text", font=font, fill=(0,255,0,255))

overlay = overlay.rotate(2.7, resample=Image.BICUBIC, center=(540,540))
im.alpha_composite(overlay)
im.save("test.png")
print("Saved test.png")
