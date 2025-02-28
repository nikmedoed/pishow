import base64
import colorsys
import random


def get_random_pastel_color():
    h = random.random()
    s = random.uniform(0.4, 0.6)
    l = random.uniform(0.75, 0.85)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b * 255))


def get_random_svg_gradient():
    gradient_type = random.choice(["linear", "radial"])

    if gradient_type == "linear":
        x1 = f"{random.randint(0, 100)}%"
        y1 = f"{random.randint(0, 100)}%"
        x2 = f"{random.randint(0, 100)}%"
        y2 = f"{random.randint(0, 100)}%"
        gradient_params = f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
    else:
        cx = f"{random.randint(20, 80)}%"
        cy = f"{random.randint(20, 80)}%"
        r = f"{random.randint(30, 60)}%"
        gradient_params = f'cx="{cx}" cy="{cy}" r="{r}"'

    num_stops = random.randint(2, 3)

    if num_stops == 2:
        offsets = [0, 100]
    else:
        offsets = [0, random.randint(20, 80), 100]
    offsets.sort()

    stops = []
    for offset in offsets:
        color = get_random_pastel_color()
        stops.append(f'<stop offset="{offset}%" style="stop-color:{color};stop-opacity:1" />')
    stops_svg = "\n          ".join(stops)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">
      <defs>
        <{gradient_type}Gradient id="grad" {gradient_params}>
          {stops_svg}
        </{gradient_type}Gradient>
      </defs>
      <rect width="400" height="400" fill="url(#grad)" />
    </svg>'''

    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode('utf-8')).decode("utf-8")
