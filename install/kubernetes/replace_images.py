import os, re

HARBOR = "10.240.125.39/cube-studio"
K8S_DIR = "/root/cube-studio-master/install/kubernetes"

SKIP_DIRS = {'crds', 'base'}
SKIP_FILES = {'operator-crd.yml', 'install-crd.yaml'}

def fix_image(img):
    q = img[0] if img and img[0] in '"\'' else ''
    clean = img.strip('"\'')
    if clean == 'auto' or '{{' in clean or '$' in clean:
        return img
    if clean.startswith('10.240.125.39'):
        return img
    original = clean
    m = re.match(r'^([a-zA-Z0-9][a-zA-Z0-9._-]*\.[a-zA-Z]{2,})/', clean)
    if m:
        rest = clean[len(m.group(0)):]
        clean = f"{HARBOR}/{rest}"
        clean = clean.replace(f"{HARBOR}/cube-studio/", f"{HARBOR}/")
    else:
        clean = f"{HARBOR}/{clean}"
    if clean != original:
        print(f"  {original} -> {clean}")
    return q + clean + q if q else clean


def process_file(fpath):
    try:
        with open(fpath, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except:
        return 0

    changed = 0
    new_lines = []
    in_crd = False

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if 'openAPIV3Schema' in line or 'validation:' in line:
            in_crd = True
        if in_crd and line and line[0] not in (' ', '\t'):
            in_crd = False

        if stripped.startswith('image:') and not stripped.startswith('imagePull'):
            if in_crd or indent >= 20 or stripped == 'image:':
                new_lines.append(line)
                continue

        if stripped.startswith('#'):
            new_lines.append(line)
            continue

        def replace_match(m):
            nonlocal changed
            prefix = m.group(1)
            quote = m.group(2) or ''
            image = m.group(3)
            if '{{' in image or '}}' in image or '$' in image:
                return m.group(0)
            full = quote + image + quote if quote else image
            new = fix_image(full)
            if new != full:
                changed += 1
            return prefix + new

        new_line = re.sub(
            r'(image:\s*)(["\']?)([a-zA-Z0-9][a-zA-Z0-9._/\-]*(?::[a-zA-Z0-9][a-zA-Z0-9._\-]*)?)',
            replace_match, line
        )
        new_lines.append(new_line)

    if changed:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        print(f"[{fpath}] +{changed}")
    return changed


total = 0
for root, dirs, files in os.walk(K8S_DIR):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if f.endswith(('.yaml', '.yml')) and f not in SKIP_FILES:
            total += process_file(os.path.join(root, f))

print(f"\nTotal: {total} images replaced")
