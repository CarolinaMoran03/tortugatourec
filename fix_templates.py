import re

with open('core/templates/core/panel/agencias.html', 'r', encoding='utf-8') as f:
    t = f.read()

# Fix 'if usuario.first_name' splitting
t = re.sub(r'\{%\s*if\s+usuario\.first_name\s*\n\s*%\}', '{% if usuario.first_name %}', t)
# Fix other common splits
t = re.sub(r'\{%\s*\n\s*if', '{% if', t)
t = re.sub(r'\{%\s*if\s+(.*?)\n\s*%\}', r'{% if \1 %}', t)

with open('core/templates/core/panel/agencias.html', 'w', encoding='utf-8') as f:
    f.write(t)

with open('core/templates/core/panel/reservas.html', 'r', encoding='utf-8') as f:
    t2 = f.read()

t2 = re.sub(r'\{%\s*if\s+r\.estado==\"([^"]+)\"\s*%\}', r'{% if r.estado == "\1" %}', t2)
t2 = re.sub(r'\{%\s*if\s*\n\s*r\.estado==\"([^"]+)\"\s*%\}', r'{% if r.estado == "\1" %}', t2)
t2 = re.sub(r'\{%\s*if(.*?)\n(.*?)%\}', r'{% if \1 \2 %}', t2)

with open('core/templates/core/panel/reservas.html', 'w', encoding='utf-8') as f:
    f.write(t2)

print("Done")
