import pygame
from time import sleep
import random
import glob
import urllib2
import os
import json

from parsing import BitsyParser

# CONFIG #
SCREEN = (480, 272)
ALIGN = "LEFT" # "LEFT" "CENTER" "RIGHT"
ROTATE = 0 # 0 1 2 3
TEXT_DELAY = 50 #ms
##########

pygame.init()
pygame.mouse.set_visible(False)

gameDisplay = pygame.display.set_mode(SCREEN)

pygame.display.set_caption('bitspy')

clock = pygame.time.Clock()

FPS = 15
font = [pygame.Surface((6, 8)) for i in xrange(256)]
arrow = pygame.Surface((5, 3))

BLK = 0x000000
WHT = 0xFFFFFF
BGR = 0x999999
TIL = 0xFF0000
SPR = 0xFFFFFF

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def chunk(l, n, i):
    return l[i:i + n]

class Launcher:
    def __init__(self):
        self.page = 0
        self.row = 0
        self.games = []
        self.screen = pygame.Surface((256, 256))
        self.selected = ""

    def event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                load_file(self.selected)
            elif event.key == pygame.K_RIGHT:
                pass
            elif event.key == pygame.K_UP:
                self.row = self.row - 1
            elif event.key == pygame.K_DOWN:
                self.row = self.row + 1
            elif event.key == pygame.K_q:
                exit = True
            elif event.key == pygame.K_ESCAPE:
                exit = True

            self.render_page()

    def render_page(self):
        rows_per_page = 32
        games = chunk(self.games, rows_per_page, self.page)
        self.selected = games[self.row]

        self.screen.fill(BLK)
        self.screen.fill((64, 0, 0), (0, self.row * 10, 256, 10))

        for i, name in enumerate(games):
            self.render_text(name, 1, i * 10 + 1)

    def render_text(self, text, x, y):
        for i, c in enumerate(text):
            self.screen.blit(font[ord(c)], (i * 6 + x, y))

class BitsyPlayer:
    def __init__(self):
        self.screen = pygame.Surface((256, 256))
        self.dialog = pygame.Surface((208, 38))

        self.frame = 0
        self.room_frame_0 = pygame.Surface((256, 256))
        self.room_frame_1 = pygame.Surface((256, 256))

        self.avatar_frame_0 = pygame.Surface((16, 16))
        self.avatar_frame_1 = pygame.Surface((16, 16))

        self.renders = {}

        self.avatar_x = 0
        self.avatar_y = 0
        self.avatar_room = None
        self.palette = None

        self.dialogue_lines = []
        self.dialogue_char = 0

        self.starting = True
        self.ending = False
        self.ended = False

        self.prev_frame = -1

    def change_world(self, world):
        self.world = world
        self.pre_render_graphics()

        self.avatar_x = self.world["sprites"]["A"]["x"]
        self.avatar_y = self.world["sprites"]["A"]["y"]

        self.set_room(self.world["rooms"][self.world["sprites"]["A"]["room"]])

        self.generate_dialogue(world["title"])

    def direction_input(self, direction):
        if self.dialogue_lines:
            self.advance_dialogue()
        else:
            if direction == 2:
                self.move_into(max(0, self.avatar_x - 1), self.avatar_y)
            elif direction == 0:
                self.move_into(min(15, self.avatar_x + 1), self.avatar_y)
            elif direction == 3:
                self.move_into(self.avatar_x, max(0, self.avatar_y - 1))
            elif direction == 1:
                self.move_into(self.avatar_x, min(15, self.avatar_y + 1))

        self.draw(self.prev_frame)

    def set_frame_count(self, frame_count):
        next_frame = (frame_count // 6) % 2

        if next_frame != self.prev_frame:
            self.draw(next_frame)
        elif self.dialogue_lines and self.draw_next_char():
            self.draw_dialog()

    def draw(self, frame):
        self.prev_frame = frame
        self.screen.fill(self.palette[0]) 

        if not self.ending and not self.starting:
            room = self.room_frame_0 if frame == 0 else self.room_frame_1
            avi = self.avatar_frame_0 if frame == 0 else self.avatar_frame_1
            self.screen.blit(room, (0, 0))

            self.screen.blit(avi, (self.avatar_x * 16, self.avatar_y * 16))

        if self.dialogue_lines:
            self.draw_dialog()

    def draw_dialog(self):
        d_x = 24
        d_y = 24

        if self.starting or self.ending:
            d_y = 108
        elif self.avatar_y < 8:
            d_y = 194

        self.screen.blit(self.dialog, (d_x, d_y))

    def avatar_occupying(self, x, y):
        return self.avatar_x == x and self.avatar_y == y

    def use_exit(self, exit):
        dest = exit["dest"]

        self.avatar_x = dest["x"]
        self.avatar_y = dest["y"]
        self.set_room(self.world["rooms"][dest["room"]])

    def use_ending(self, ending):
        self.generate_dialogue(world["endings"][ending["id"]]["text"])
        self.ending = True

    def move_into(self, x, y):
        room = self.avatar_room
        tile = self.avatar_room["tilemap"][y][x]

        for sprite in self.world["sprites"].values():
            if sprite["room"] == self.avatar_room["id"] and x == sprite["x"] and y == sprite["y"] and sprite["id"] != "A":
                self.generate_dialogue(self.world["dialogues"][sprite["dialogue"]]["text"])
                return

        if not tile in room["walls"]:
            self.avatar_x = x
            self.avatar_y = y

        for ending in room["endings"]:
            if self.avatar_occupying(ending["x"], ending["y"]):
                self.use_ending(ending)
                return

        for exit in room["exits"]:
            if self.avatar_occupying(exit["x"], exit["y"]):
                self.use_exit(exit)
                return

    def pre_render_graphics(self):
        for sprite in self.world["sprites"].itervalues():
            self.renders["sprite_" + sprite["id"]] = render(sprite["graphic"], SPR)

        for tile in self.world["tiles"].itervalues():
            self.renders["tile_" + tile["id"]] = render(tile["graphic"], TIL)

    def pre_render_room(self):
        self.render_room_frame(self.room_frame_0, self.avatar_room, 0)
        self.render_room_frame(self.room_frame_1, self.avatar_room, 1)

        self.avatar_frame_0.blit(self.renders["sprite_A"][ 0], (0, 0))
        self.avatar_frame_1.blit(self.renders["sprite_A"][-1], (0, 0))

        recolor(self.avatar_frame_0, self.palette)
        recolor(self.avatar_frame_1, self.palette)

    def render_room_frame(self, surface, room, frame):
        for y in xrange(0, 16):
            for x in xrange(0, 16):
                id = room["tilemap"][y][x]
                if id == "0":
                    surface.fill(BGR, (x * 16, y * 16, 16, 16))
                    continue
                tile = self.world["tiles"][id]

                surface.blit(self.renders["tile_" + id][frame], (x * 16, y * 16))

                #draw_graphic(surface, x, y, tile, frame, 1)

        for sprite in self.world["sprites"].values():
            if sprite["id"] != "A" and sprite["room"] == room["id"]:
                surface.blit(self.renders["sprite_" + sprite["id"]][frame], (sprite["x"] * 16, sprite["y"] * 16))

        recolor(surface, self.palette)

    def set_room(self, room):
        self.avatar_room = room
        self.palette = self.world["palettes"][room["palette"]]["colors"]
        self.pre_render_room()

    def advance_dialogue(self):
        if self.skip_dialogue():
            return

        if self.ending:
            self.ended = True

        if self.starting:
            self.starting = False

        self.dialogue_lines = self.dialogue_lines[2:]

        self.dialog.fill(BLK)
        self.dialogue_char = 0
        self.draw_next_char()

    def skip_dialogue(self):
        skipped = False

        while self.draw_next_char():
            skipped = True

        return skipped

    def draw_next_char(self):
        xoff = 8
        yoff = 8
        chars = 32
        demo = "".join(line.ljust(chars) for line in self.dialogue_lines[:2])
        demo = demo[:chars*2]

        if self.dialogue_char >= len(demo):
            return False

        x = self.dialogue_char % 32
        y = self.dialogue_char // 32

        c = demo[self.dialogue_char]
        self.dialog.blit(font[ord(c)], (xoff + x * 6, yoff + y * (8 + 4)))

        self.dialogue_char += 1 
        while self.dialogue_char < len(demo) and demo[self.dialogue_char].strip() == "":
            self.dialogue_char += 1 

        if self.dialogue_char == len(demo):
            self.dialog.blit(arrow, (xoff + 182, yoff + 20)) 

        return True

    def generate_dialogue(self, text):
        lines = text.split("\n")
        rows = []
        limit = 32

        for line in lines:
            if len(line) > limit:
                row = ""
                words = line.split(" ")
                next = 0

                while next < len(words):
                    if len(words[next]) > limit:
                        space = limit - 1 - len(row)
                        rows.append(line[:left])
                        words[next] = line[left:]
                        next -= 1
                    elif len(row) + 1 + len(words[next]) > limit:
                        rows.append(row)
                        row = words[next]
                    elif row:
                        row += " " + words[next]
                    else:
                        row = words[next]

                    next += 1 

                if row:
                    rows.append(row)
            else:
                rows.append(line)

        self.dialogue_lines.extend(rows)

def load_file(name):
    root = os.path.dirname(__file__)
    file = os.path.join(root, "games", name + ".bitsy.txt")
    music = os.path.join(root, "games", name + ".ogg")

    with open(file, "rb") as file:
        data = file.read().replace("\r\n", "\n")
        lines = data.split("\n")
        parser = BitsyParser(lines)
        parser.parse()
        world = parser.world

        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.load(music)
            pygame.mixer.music.play(-1)
        except Exception as exception:
            print(exception)

        return world

def load_game():
    off = 8

    gameDisplay.fill(WHT)
    pygame.draw.rect(gameDisplay, 
                     BLK, 
                     [off, off, SCREEN[0] - off * 2, SCREEN[1] - off * 2])
    pygame.display.update()

    game = {}

    data = ""

    root = os.path.dirname(__file__)
    search = os.path.join(root, "games", "*.bitsy.txt")

    url = r"http://api.github.com/gists/1b7cc99139948d1f908962e4ef39b7fb"
    data = json.load(urllib2.urlopen(url))

    for name, entry in data["files"].iteritems():
        dest = os.path.join(root, "games", name)
        open(dest, "wb").write(entry["content"])

    for file in glob.glob(search):
        path, filename = os.path.split(file)
        name, _, _ = filename.split(".")

        launcher.games.append(name)
    
def draw_graphic(surface, ox, oy, tile, anim, primary):
    graphic = tile["graphic"]
    frame = graphic[anim % len(graphic)]

    for y in xrange(0, 8):
        for x in xrange(0, 8):
            color = primary if frame[y][x] else 0
            pygame.draw.rect(surface, color, [x * 2 + ox * 16, y * 2 + oy * 16, 2, 2])

def render(graphic, primary):
    renders = [pygame.Surface((16, 16)), pygame.Surface((16, 16))]

    for i in xrange(2):
        for y in xrange(0, 8):
            for x in xrange(0, 8):
                color = primary if graphic[i % len(graphic)][y][x] else BGR
                pygame.draw.rect(renders[i], color, [x * 2, y * 2, 2, 2])

    return renders

def render_font():
    global arrow
    data = ""

    root = os.path.dirname(__file__)

    with open(os.path.join(root, "font.txt"), "rb") as file:
        data = file.read().replace("\r\n", "\n")

    sections = data.split("\n\n")

    for i, section in enumerate(sections):
        pixels = pygame.PixelArray(font[i])

        for y, row in enumerate(section.split("\n")):
            for x, char in enumerate(row):
                pixels[x, y] = BLK if char == "0" else WHT

    arrowdata = """11111\n01110\n00100"""
    pixels = pygame.PixelArray(arrow)

    for y, row in enumerate(arrowdata.split("\n")):
        for x, char in enumerate(row):
            pixels[x, y] = BLK if char == "0" else WHT

    arrow = pygame.transform.scale(arrow, (10, 6))

def recolor(surface, palette):
    pixels = pygame.PixelArray(surface)
    pixels.replace(BGR, palette[0])
    pixels.replace(TIL, palette[1])
    pixels.replace(SPR, palette[2])

launcher = Launcher()
player = BitsyPlayer()

def draw():
    gameDisplay.fill(BLK)

    gap_h = SCREEN[0] - 256
    gap_v = SCREEN[1] - 256
    pad_x = gap_h // 2
    pad_y = gap_v // 2

    if ALIGN == "LEFT":
        pad_x = pad_y
    elif ALIGN == "CENTER":
        pad_x = gap_h // 2
    elif ALIGN == "RIGHT":
        pad_x = SCREEN[0] - 256 - pad_y

    #player.screen.blit(launcher.screen, (0, 0))
    
    screen2 = pygame.transform.rotate(player.screen, -90 * ROTATE)
    #screen2 = pygame.transform.scale(screen, (512, 512))
    #screen2 = pygame.transform.smoothscale(screen, ((272, 272)))
    #pad_y = 0
    gameDisplay.blit(screen2, (pad_x, pad_y))

    pygame.display.update()

def game_loop():
    global ROTATE, ALIGN

    dir = -1
    key = False
    exit = False
    anim = 0

    player.change_world(load_file(launcher.games[0]))

    while not player.ended and not exit:
        for event in pygame.event.get():
            launcher.event(event)

            if event.type == pygame.QUIT:
                exit = True
            if event.type == pygame.KEYDOWN:
                key = True

                if event.key == pygame.K_LEFT:
                    dir = 2
                elif event.key == pygame.K_RIGHT:
                    dir = 0
                elif event.key == pygame.K_UP:
                    dir = 3
                elif event.key == pygame.K_DOWN:
                    dir = 1
                elif event.key == pygame.K_q:
                    exit = True
                elif event.key == pygame.K_ESCAPE:
                    exit = True
                elif event.key == pygame.K_0:
                    ROTATE = 0
                elif event.key == pygame.K_1:
                    ROTATE = 1
                elif event.key == pygame.K_2:
                    ROTATE = 2
                elif event.key == pygame.K_3:
                    ROTATE = 3
                elif event.key == pygame.K_i:
                    ALIGN = "LEFT"
                elif event.key == pygame.K_o:
                    ALIGN = "CENTER"
                elif event.key == pygame.K_p:
                    ALIGN = "RIGHT"

        if anim % 3 == 0 and key:
            player.direction_input((dir - ROTATE) % 4)
            dir = -1
            key = False

        player.set_frame_count(anim)
        draw()
        
        clock.tick(FPS)
        anim += 1

    pygame.mouse.set_visible(True)
    pygame.quit()
    quit()

if __name__ == "__main__":
    render_font()
    load_game()
    #launcher.render_page()
    game_loop()