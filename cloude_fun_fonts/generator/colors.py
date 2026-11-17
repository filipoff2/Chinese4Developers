"""Color tables for the font generator.

All colors end up as entries in CPAL palette 0 (Office and browsers only use palette 0):
the 20 color groups first, then the 3 role colors.
"""

# The 20 color groups (same as the PoC).
COLOR_GROUPS = [
    ("Imperial Gold", "#D4A017"),
    ("Chinese New Year", "#D7263D"),
    ("Jade", "#00A86B"),
    ("Porcelain Blue", "#1F4E9C"),
    ("Dragon Fire", "#FF4500"),
    ("Lotus Pink", "#E75480"),
    ("Bamboo Green", "#5B8C2A"),
    ("Phoenix", "#FF8C00"),
    ("Cyberpunk", "#B000FF"),
    ("Chrome", "#8A9BA8"),
    ("Ocean", "#0077BE"),
    ("Sunset", "#FD5E53"),
    ("Royal Purple", "#6A0DAD"),
    ("Emerald", "#009B77"),
    ("Sakura", "#F4A7B9"),
    ("Autumn", "#C1440E"),
    ("Ice Crystal", "#5BC0EB"),
    ("Galaxy", "#2E1A47"),
    ("Bronze", "#CD7F32"),
    ("Rainbow", "#E91E63"),
]

# Component roles from hanzi-120.json, same colors as the legend in
# 120_Common_Chinese_Characters_Component_Colored.md.
ROLE_COLORS = [
    ("semantic", "#1E90FF"),
    ("phonetic", "#2A9D8F"),
    ("neutral", "#000000"),
]

# Kangxi radical number (Unihan kRSUnicode) -> color group, grouped by meaning.
# Radicals not listed here get COLOR_GROUPS[radical % 20].
RADICAL_GROUPS = {
    9: "Royal Purple",       # 人 亻 person
    10: "Royal Purple",      # 儿 legs
    18: "Chrome",            # 刀 刂 knife
    19: "Dragon Fire",       # 力 strength
    30: "Chinese New Year",  # 口 mouth
    31: "Chinese New Year",  # 囗 enclosure
    32: "Bronze",            # 土 earth
    38: "Lotus Pink",        # 女 woman
    39: "Lotus Pink",        # 子 child
    40: "Galaxy",            # 宀 roof
    46: "Emerald",           # 山 mountain
    53: "Galaxy",            # 广 shelter
    60: "Chrome",            # 彳 step
    61: "Sakura",            # 心 忄 heart
    64: "Phoenix",           # 手 扌 hand
    66: "Phoenix",           # 攴 攵 strike
    72: "Sunset",            # 日 sun
    73: "Sunset",            # 曰 say
    74: "Ice Crystal",       # 月 moon
    75: "Bamboo Green",      # 木 tree
    85: "Ocean",             # 水 氵 water
    86: "Dragon Fire",       # 火 灬 fire
    94: "Autumn",            # 犬 犭 dog
    96: "Jade",              # 玉 王 jade
    102: "Bronze",           # 田 field
    104: "Chrome",           # 疒 sickness
    109: "Galaxy",           # 目 eye
    112: "Chrome",           # 石 stone
    113: "Imperial Gold",    # 示 礻 spirit
    115: "Bamboo Green",     # 禾 grain
    116: "Galaxy",           # 穴 cave
    118: "Bamboo Green",     # 竹 bamboo
    119: "Autumn",           # 米 rice
    120: "Cyberpunk",        # 糸 纟 silk
    130: "Ice Crystal",      # 肉 月 meat
    140: "Jade",             # 艸 艹 grass
    142: "Emerald",          # 虫 insect
    145: "Lotus Pink",       # 衣 衤 clothing
    147: "Galaxy",           # 見 见 see
    149: "Porcelain Blue",   # 言 讠 speech
    154: "Imperial Gold",    # 貝 贝 shell, money
    157: "Autumn",           # 足 foot
    159: "Chrome",           # 車 车 cart
    162: "Chrome",           # 辵 辶 walk
    163: "Bronze",           # 邑 阝 (right) city
    167: "Imperial Gold",    # 金 钅 metal
    169: "Bronze",           # 門 门 gate
    170: "Emerald",          # 阜 阝 (left) mound
    173: "Ice Crystal",      # 雨 rain
    181: "Rainbow",          # 頁 页 head
    184: "Autumn",           # 食 饣 food
    187: "Autumn",           # 馬 马 horse
    195: "Ocean",            # 魚 鱼 fish
    196: "Phoenix",          # 鳥 鸟 bird
}

# Component forms that count as the same component when matching hanzi-120.json
# components against Make Me a Hanzi decompositions.
COMPONENT_VARIANTS = {
    "亻": "人", "氵": "水", "扌": "手", "讠": "言", "钅": "金", "纟": "糸",
    "忄": "心", "刂": "刀", "辶": "辵", "饣": "食", "礻": "示", "衤": "衣",
    "王": "玉", "犭": "犬", "艹": "艸", "罒": "网", "灬": "火", "尢": "尤",
}


def group_for_radical(radical):
    """Return (group name, mapped by meaning?) for a Kangxi radical number."""
    if radical in RADICAL_GROUPS:
        return RADICAL_GROUPS[radical], True
    return COLOR_GROUPS[radical % len(COLOR_GROUPS)][0], False
