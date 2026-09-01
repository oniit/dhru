import yaml

def normalize_multi_choice_value(val):
    if not val:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        return [val]
    return [str(val)]

data = yaml.safe_load(open('config/choices.yaml', encoding='utf-8'))
position_details = data.get("position_details", [])

ids = set()
choice_id = "p_panitia_ospek"

if choice_id in ids:
    ids.discard(choice_id)
else:
    ids.add(choice_id)

opts = position_details

def keyboard_for_multi_choices(field_key, choices_key, selected, toggle_prefix, done_prefix, options):
    opts = options
    rows = []
    for item in opts:
        cid = str(item.get("id", ""))
        lab = str(item.get("label", cid))
        mark = "✓ " if cid in selected else ""
        cb = f"{toggle_prefix}:{field_key}:{cid}"[:64]
        rows.append([mark + lab, cb])
    return rows

kb = keyboard_for_multi_choices("position_detail", "position_details", ids, toggle_prefix="mec", done_prefix="med", options=opts)

for r in kb:
    if "Panitia Ospek" in r[0]:
        print(r)
