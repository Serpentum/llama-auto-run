def sanitize_args(args_list):
    clean = []
    for a in args_list:
        a = a.replace("^", " ").strip()
        if a:
            clean.append(a)
    return clean


def args_list_to_string(args):
    parts = []
    for arg in args:
        if " " in arg or '"' in arg or "'" in arg:
            parts.append(f"'{arg}'")
        else:
            parts.append(arg)
    return " ".join(parts)


def string_to_args_list(text):
    text = text.replace("^", " ")
    tokens = []
    current = []
    in_quotes = False
    quote_char = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quotes:
            if ch == quote_char:
                in_quotes = False
            else:
                current.append(ch)
        elif ch in ('"', "'"):
            in_quotes = True
            quote_char = ch
        elif ch == " ":
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
        i += 1
    if current:
        tokens.append("".join(current))
    return [t.strip() for t in tokens if t.strip()]


def get_model_from_args(args_list):
    for i, a in enumerate(args_list):
        if a == "--model" and i + 1 < len(args_list):
            return args_list[i + 1]
    return None
