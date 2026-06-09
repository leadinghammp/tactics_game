from PIL import Image, ImageDraw, ImageFilter
import os, json

TILE_W = 32
TILE_H = 16
ISO_DEPTH = 8

def make_iso_floor(color_top, color_side=None, size=(32,24)):
    w,h = size
    img = Image.new("RGBA",(w,h),(0,0,0,0))
    draw = ImageDraw.Draw(img)
    hw = w//2; qh = h//3
    top = [(hw,0),(w-1,qh),(hw,qh*2),(0,qh)]
    draw.polygon(top, fill=color_top+(255,))
    for i in range(len(top)):
        x0,y0 = top[i]; x1,y1 = top[(i+1)%len(top)]
        bright = max(0, color_top[0]-30), max(0, color_top[1]-30), max(0, color_top[2]-30)
        draw.line([(x0,y0),(x1,y1)], fill=bright+(200,), width=1)
    return img

def make_iso_wall(color_top, color_front, color_right, size=(32,32)):
    w,h = size
    img = Image.new("RGBA",(w,h),(0,0,0,0))
    draw = ImageDraw.Draw(img)
    hw = w//2; th = h//3
    top   = [(hw,0),(w-1,th),(hw,th*2),(0,th)]
    front = [(0,th),(hw,th*2),(hw,h-1),(0,h-1-th//2)]
    right = [(hw,th*2),(w-1,th),(w-1,h-1-th//2),(hw,h-1)]
    draw.polygon(top,   fill=color_top+(255,))
    draw.polygon(front, fill=color_front+(255,))
    draw.polygon(right, fill=color_right+(255,))
    for poly in [top,front,right]:
        pts = [(p[0],p[1]) for p in poly]
        draw.line(pts+[pts[0]], fill=(0,0,0,80), width=1)
    return img

def make_iso_door(open_pct=0.0):
    base = make_iso_wall((100,80,60),(130,100,70),(80,60,40))
    draw = ImageDraw.Draw(base)
    door_x = 10; door_y = 14; door_w = 12; door_h = 14
    open_h = int(door_h*open_pct)
    if door_y+open_h < door_y+door_h:
        draw.rectangle([door_x, door_y+open_h, door_x+door_w, door_y+door_h], fill=(20,10,5,255))
    if door_y+open_h+1 < door_y+door_h-1:
        draw.rectangle([door_x+1, door_y+open_h+1, door_x+door_w//2-1, door_y+door_h-1], fill=(100,70,40,255))
        draw.rectangle([door_x+door_w//2+1, door_y+open_h+1, door_x+door_w-1, door_y+door_h-1], fill=(100,70,40,255))
    draw.point((door_x+door_w//2, door_y+min(door_h//2+open_h, door_h-1)), fill=(220,180,50,255))
    return base

def build_iso_tileset(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    tiles = {
        "iso_floor_stone": make_iso_floor((65,55,45)),
        "iso_floor_dark":  make_iso_floor((45,38,32)),
        "iso_wall_stone":  make_iso_wall((105,95,85),(90,80,70),(70,60,52)),
        "iso_door_closed": make_iso_door(0.0),
        "iso_door_open":   make_iso_door(1.0),
        "iso_floor_chest": make_iso_floor((130,100,30)),
    }
    for name, img in tiles.items():
        img.save(os.path.join(output_dir, f"{name}.png"))
    return list(tiles.keys())

def generate_vfx_sprites(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for frame in range(4):
        img = Image.new("RGBA",(16,16),(0,0,0,0))
        draw = ImageDraw.Draw(img)
        r = 2+frame*2; alpha = max(0, 255-frame*60)
        cx=cy=8
        draw.ellipse([cx-r,cy-r,cx+r,cy+r], fill=(255,80,20,alpha))
        if r>2:
            draw.ellipse([cx-r+2,cy-r+2,cx+r-2,cy+r-2], fill=(255,200,50,alpha))
        img.save(os.path.join(output_dir, f"hit_{frame}.png"))
    for frame in range(4):
        img = Image.new("RGBA",(16,16),(0,0,0,0))
        draw = ImageDraw.Draw(img)
        r = 1+frame; alpha = max(0, 200-frame*50)
        for i in range(6):
            import math
            angle = (i/6)*math.pi*2 + frame*0.3
            ex = int(8+math.cos(angle)*(2+frame*2))
            ey = int(8+math.sin(angle)*(2+frame*2))
            draw.ellipse([ex-1,ey-1,ex+1,ey+1], fill=(180,60,220,alpha))
        img.save(os.path.join(output_dir, f"magic_{frame}.png"))

def make_minimap(level_dict, fov_mask, output_path, scale=2):
    w = level_dict["width"]; h = level_dict["height"]
    img = Image.new("RGBA",(w*scale,h*scale),(0,0,0,255))
    COLORS = {0:(0,0,0),1:(80,70,60),2:(140,130,120),3:(160,110,50),4:(60,80,180),5:(180,160,40)}
    tiles = level_dict["tiles"]
    for y in range(h):
        for x in range(w):
            if fov_mask[y][x]: continue
            t = tiles[y][x]
            col = COLORS.get(t,(40,40,40))
            for dy in range(scale):
                for dx in range(scale):
                    img.putpixel((x*scale+dx,y*scale+dy),col+(255,))
    px,py = level_dict["player_start"]
    for dy in range(scale):
        for dx in range(scale):
            img.putpixel((px*scale+dx,py*scale+dy),(50,150,255,255))
    img.save(output_path)
    return output_path

if __name__=="__main__":
    keys = build_iso_tileset("../../godot/assets/sprites/iso")
    generate_vfx_sprites("../../godot/assets/sprites/vfx")
    print("ISO tileset:", keys)
    print("VFX sprites generated")
