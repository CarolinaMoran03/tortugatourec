import sys

filepath = r"c:\Users\CM\Documents\tortugatour (1)\tortugatour\tortugatour\core\templates\core\panel\secretaria_reservar.html"

with open(filepath, "r", encoding="utf-8", newline="") as f:
    text = f.read()

text = text.replace('destino.id|stringformat:"s"==destino_id', 'destino.id|stringformat:"s" == destino_id')

with open(filepath, "w", encoding="utf-8", newline="") as f:
    f.write(text)

print("Fixed spacing in file")
