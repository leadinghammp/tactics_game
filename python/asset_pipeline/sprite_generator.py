from PIL import Image, ImageDraw
import json, os, math, random

SPRITE_SIZE = 16
DIRECTIONS = ["n","ne","e","se","s","sw","w","nw"]
PALETTE = {
    "skin":    [(255,220,185),(230,190,150),(200,160,120)],
    "armor":   [(80,80,100),(120,120,150),(160,160,190)],
    "weapon":  [(180,140,60),(210,170,80),(240,200,100)],
    "enemy":   [(180,40,40),(140,20,20),(220,60,60)],
    "floor":   [(60,50,40),(80,65,50),(100,80,60)],
    "wall":    [(100,90,80),(130,115,100),(80,70,60)],
    "door":    [(120,80,40),(160,110,60),(90,60,30)],
    "item":    [(60,180,220),(40,140,180),(80,200,255)],
}

TIERS = {1:"common",2:"uncommon",3:"rare",4:"epic",5:"legendary"}
TIER_COLORS = {
    1:(180,180,180),2:(80,200,80),3:(60,100,220),
    4:(160,60,220),5:(220,160,40)
}

def pixel(draw, x, y, color): draw.point((x,y), fill=color)

def lerp_color(a, b, t):
    return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))

def draw_character_frame(draw, direction, frame, char_type="player"):
    cx, cy = 8, 8
    dx = {"n":0,"ne":1,"e":2,"se":1,"s":0,"sw":-1,"w":-2,"nw":-1}[direction]
    dy = {"n":-1,"ne":-1,"e":0,"se":1,"s":1,"sw":1,"w":0,"nw":-1}[direction]
    base = PALETTE["skin"][0] if char_type=="player" else PALETTE["enemy"][0]
    dark = PALETTE["skin"][2] if char_type=="player" else PALETTE["enemy"][2]
    armor = PALETTE["armor"][0]
    bob = [0,1,0,-1][frame%4]
    for px in range(cx-2, cx+3):
        for py in range(cy-5+bob, cy-2+bob):
            draw.point((px,py), fill=base)
    draw.point((cx+dx-1, cy-4+bob), fill=dark)
    draw.point((cx+dx+1, cy-4+bob), fill=dark)
    draw.point((cx+dx, cy-3+bob), fill=dark)
    for px in range(cx-2, cx+3):
        for py in range(cy-2+bob, cy+2+bob):
            draw.point((px,py), fill=armor)
    leg_off = [0,1,0,-1][frame%4]
    draw.point((cx-1, cy+2+bob+leg_off), fill=base)
    draw.point((cx+1, cy+2+bob-leg_off), fill=base)
    draw.point((cx-1, cy+3+bob+leg_off), fill=base)
    draw.point((cx+1, cy+3+bob-leg_off), fill=base)
    if char_type=="player":
        draw.point((cx-3, cy-1+bob), fill=PALETTE["weapon"][0])
        draw.point((cx-3, cy-2+bob), fill=PALETTE["weapon"][1])
        draw.point((cx-4, cy-3+bob), fill=PALETTE["weapon"][1])

def generate_character_spritesheet(path, char_type="player"):
    frames = 4
    sheet = Image.new("RGBA",(SPRITE_SIZE*8, SPRITE_SIZE*frames),(0,0,0,0))
    for di, direction in enumerate(DIRECTIONS):
        for frame in range(frames):
            img = Image.new("RGBA",(SPRITE_SIZE,SPRITE_SIZE),(0,0,0,0))
            draw = ImageDraw.Draw(img)
            draw_character_frame(draw, direction, frame, char_type)
            sheet.paste(img,(di*SPRITE_SIZE, frame*SPRITE_SIZE))
    sheet.save(path)
    return path

def generate_tile(tile_type, variant=0):
    img = Image.new("RGBA",(SPRITE_SIZE,SPRITE_SIZE),(0,0,0,0))
    draw = ImageDraw.Draw(img)
    if tile_type=="floor":
        base = PALETTE["floor"][variant%3]
        for x in range(SPRITE_SIZE):
            for y in range(SPRITE_SIZE):
                noise = random.randint(-10,10)
                c = tuple(max(0,min(255,v+noise)) for v in base)
                draw.point((x,y), fill=c+(255,))
        for _ in range(4):
            x,y = random.randint(0,15), random.randint(0,15)
            draw.point((x,y), fill=tuple(max(0,v-20) for v in base)+(255,))
    elif tile_type=="wall":
        base = PALETTE["wall"][variant%3]
        for x in range(SPRITE_SIZE):
            for y in range(SPRITE_SIZE):
                noise = random.randint(-15,15)
                c = tuple(max(0,min(255,v+noise)) for v in base)
                draw.point((x,y), fill=c+(255,))
        for y in [4,8,12]:
            for x in range(SPRITE_SIZE):
                draw.point((x,y), fill=tuple(max(0,v-30) for v in base)+(255,))
    elif tile_type=="door":
        base = PALETTE["door"][1]
        dark = PALETTE["door"][2]
        for x in range(SPRITE_SIZE):
            for y in range(SPRITE_SIZE):
                draw.point((x,y), fill=base+(255,))
        for x in [3,4,11,12]:
            for y in range(2,14):
                draw.point((x,y), fill=dark+(255,))
        for y in [2,13]:
            for x in range(3,13):
                draw.point((x,y), fill=dark+(255,))
        draw.point((7,7), fill=(200,200,50,255))
        draw.point((8,7), fill=(200,200,50,255))
    elif tile_type=="stairs":
        base = (70,60,50)
        for x in range(SPRITE_SIZE):
            for y in range(SPRITE_SIZE):
                draw.point((x,y), fill=base+(255,))
        for i in range(4):
            y = 3+i*3
            for x in range(2,14):
                draw.point((x,y), fill=(100,90,80,255))
                draw.point((x,y+1), fill=(50,45,40,255))
    return img

def generate_item_sprite(item_type, tier=1):
    img = Image.new("RGBA",(SPRITE_SIZE,SPRITE_SIZE),(0,0,0,0))
    draw = ImageDraw.Draw(img)
    tc = TIER_COLORS[tier]
    if item_type=="sword":
        for y in range(3,13):
            draw.point((8,y), fill=tc+(255,))
            draw.point((7,y), fill=tuple(max(0,v-40) for v in tc)+(255,))
        draw.point((6,10), fill=tc+(255,))
        draw.point((10,10), fill=tc+(255,))
        draw.point((8,3), fill=(220,220,220,255))
    elif item_type=="shield":
        for x in range(5,11):
            for y in range(4,12):
                if abs(x-8)<3 or y<10:
                    draw.point((x,y), fill=tc+(255,))
        draw.point((8,7), fill=(220,220,100,255))
    elif item_type=="staff":
        for y in range(2,14):
            draw.point((8,y), fill=tc+(255,))
        for dx in range(-2,3):
            draw.point((8+dx,4), fill=(200,100,220,255))
        draw.point((8,2), fill=(240,200,255,255))
    elif item_type=="armor":
        for x in range(5,11):
            for y in range(5,13):
                draw.point((x,y), fill=tc+(255,))
        for x in range(3,13):
            for y in range(5,8):
                draw.point((x,y), fill=tc+(255,))
    elif item_type=="potion":
        for x in range(6,10):
            for y in range(4,13):
                draw.point((x,y), fill=tc+(200,))
        for x in range(7,9):
            for y in range(2,5):
                draw.point((x,y), fill=(180,180,180,255))
        draw.point((7,4), fill=(80,80,80,255))
        draw.point((8,4), fill=(80,80,80,255))
    return img

def generate_all_assets(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    meta = {}
    for ct in ["player","goblin","skeleton","orc","dragon"]:
        p = os.path.join(output_dir, f"{ct}_sheet.png")
        generate_character_spritesheet(p, "player" if ct=="player" else "enemy")
        meta[ct] = {"path":p,"type":"character","directions":8,"frames":4,"size":SPRITE_SIZE}
    for tt in ["floor","wall","door","stairs"]:
        for v in range(3):
            p = os.path.join(output_dir, f"{tt}_{v}.png")
            generate_tile(tt,v).save(p)
            meta[f"{tt}_{v}"] = {"path":p,"type":"tile","size":SPRITE_SIZE}
    items = ["sword","shield","staff","armor","potion"]
    for it in items:
        for tier in range(1,6):
            p = os.path.join(output_dir, f"item_{it}_t{tier}.png")
            generate_item_sprite(it,tier).save(p)
            meta[f"{it}_t{tier}"] = {
                "path":p,"type":"item","item_type":it,
                "tier":tier,"tier_name":TIERS[tier],"size":SPRITE_SIZE
            }
    meta_path = os.path.join(output_dir,"asset_manifest.json")
    with open(meta_path,"w") as f:
        json.dump(meta,f,indent=2)
    return meta_path

if __name__=="__main__":
    p = generate_all_assets("../../godot/assets/sprites")
    print(f"Assets generated. Manifest: {p}")
