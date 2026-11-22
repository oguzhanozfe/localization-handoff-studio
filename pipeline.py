"""Validate localized JSON strings and plural forms before packaging a handoff."""

from collections import Counter
import json
import re
import string

TITLE = "Localization Handoff Studio"
DESCRIPTION = "Detect placeholder, plural and glossary drift, then export approved repairs or a translator queue."
PROMPT = "Explain the key-level evidence for each localization action. Keep glossary policy separate from linguistic correctness. Do not claim suggested repairs are fluent merely because they pass structural checks."
CATEGORIES = {"zero", "one", "two", "few", "many", "other"}
PRINTF = re.compile(r"%%|%(?:(\d+)\$)?([sdif])")


def rows(data, key, limit=250, empty=False):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list) or len(value) > limit or (not value and not empty):
        raise ValueError(
            f"{key} must be a list with {'0' if empty else '1'} to {limit} entries"
        )
    if any(not isinstance(entry, dict) for entry in value):
        raise ValueError(f"Every {key} entry must be an object")
    return value


def text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank text, at most {limit} characters")
    return value.strip()


def selected(evidence, approved):
    by_id = {c["id"]: c for c in evidence["candidates"]}
    result = []
    seen = set()
    for item in approved:
        key = item.get("id") if isinstance(item, dict) else None
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise ValueError("Unknown or duplicate approval")
        seen.add(key)
        result.append(by_id[key])
    return result


def bundle(value, name):
    if not isinstance(value, dict) or len(value) > 500:
        raise ValueError(f"{name} must be a JSON object of up to 500 keys")
    for key, entry in value.items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*", key)
            or len(key) > 180
        ):
            raise ValueError("Use simple dot-separated resource keys")
        if isinstance(entry, str):
            if len(entry) > 4000:
                raise ValueError("A resource string exceeds 4000 characters")
        elif (
            not isinstance(entry, dict)
            or not set(entry) <= CATEGORIES
            or any(not isinstance(v, str) or len(v) > 4000 for v in entry.values())
        ):
            raise ValueError("Resources must be strings or plural-category objects")
    return value


def placeholders(value):
    named = Counter()
    ordered = []
    for _, field, spec, conversion in string.Formatter().parse(value):
        if field is not None:
            if not re.fullmatch(r"[A-Za-z_]\w*", field) or spec or conversion:
                raise ValueError("Only simple named brace placeholders are supported")
            named["{" + field + "}"] += 1
    for m in PRINTF.finditer(value):
        if m[0] == "%%":
            continue
        if m[1]:
            named[m[0]] += 1
        else:
            ordered.append(m[2])
    return named, ordered


def issues(source, target, forms, terms):
    if target is None:
        return ["Missing target key"]
    plural = isinstance(source, dict)
    if plural != isinstance(target, dict):
        return ["String/plural shape mismatch"]
    faults = []
    if plural:
        missing = set(forms) - set(target)
        if missing:
            faults.append("Missing plural forms: " + ", ".join(sorted(missing)))
        pairs = [
            (cat, source.get(cat, source["other"]), dst) for cat, dst in target.items()
        ]
    else:
        pairs = [("text", source, target)]
    for form, src, dst in pairs:
        if not dst.strip():
            faults.append(form + ": blank translation")
        try:
            if placeholders(src) != placeholders(dst):
                faults.append(form + ": placeholder contract differs")
        except ValueError:
            faults.append(form + ": malformed or unsupported placeholder")
        for left, right in terms:
            if re.search(
                r"(?<!\w)" + re.escape(left) + r"(?!\w)", src, re.I
            ) and not re.search(r"(?<!\w)" + re.escape(right) + r"(?!\w)", dst, re.I):
                faults.append(f"{form}: glossary requires '{right}' for '{left}'")
    return faults


def prepare(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    locale = text(data.get("locale"), "locale", 24)
    if not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", locale):
        raise ValueError("Invalid locale code")
    src = bundle(data.get("source"), "source")
    dst = bundle(data.get("target"), "target")
    fixes = bundle(data.get("repairs", {}), "repairs")
    if not src or not set(fixes) <= set(src):
        raise ValueError("Provide source keys and known repair keys")
    forms = data.get("required_plural_forms", ["other"])
    if (
        not isinstance(forms, list)
        or any(not isinstance(f, str) or f not in CATEGORIES for f in forms)
        or "other" not in forms
    ):
        raise ValueError("Specify plural categories, including other")
    terms = (
        [
            (
                text(g.get("source"), "glossary source"),
                text(g.get("target"), "glossary target"),
            )
            for g in rows(data, "glossary", 60, empty=True)
        ]
        if "glossary" in data
        else []
    )
    records = []
    candidates = []
    for key, source in src.items():
        if isinstance(source, dict) and "other" not in source:
            raise ValueError("Source plurals need an other form: " + key)
        for original in source.values() if isinstance(source, dict) else [source]:
            try:
                placeholders(original)
            except ValueError as exc:
                raise ValueError("Invalid source placeholder for " + key) from exc
        problems = issues(source, dst.get(key), forms, terms)
        rec = {
            "id": "key:" + key,
            "key": key,
            "source": source,
            "current": dst.get(key),
            "issues": problems,
        }
        records.append(rec)
        if not problems:
            continue
        proposed = fixes.get(key)
        reject = issues(source, proposed, forms, terms) if proposed is not None else []
        apply = proposed is not None and not reject
        if reject:
            rec["proposed_repair_issues"] = reject
        cand = {
            "id": "review:" + key,
            "action": (
                "Apply supplied translation for " if apply else "Send to translator: "
            )
            + key,
            "evidence_ids": [rec["id"]],
            "key": key,
            "kind": "apply" if apply else "queue",
        }
        if apply:
            cand["replacement"] = proposed
        candidates.append(cand)
    orphans = sorted(set(dst) - set(src))
    records.extend(
        {"id": "orphan:" + k, "key": k, "issues": ["Target-only key retained"]}
        for k in orphans
    )
    return {
        "summary": f"{len(candidates)} source keys need attention; {len(orphans)} target-only keys will be retained.",
        "metrics": {
            "Source keys": len(src),
            "Review items": len(candidates),
            "Valid supplied fixes": sum(c["kind"] == "apply" for c in candidates),
        },
        "records": records,
        "candidates": candidates,
    }


def export(data, evidence, approved):
    result = dict(data["target"])
    queue = []
    by_id = {r["id"]: r for r in evidence["records"]}
    for c in selected(evidence, approved):
        if c["kind"] == "apply":
            result[c["key"]] = c["replacement"]
        else:
            r = by_id[c["evidence_ids"][0]]
            queue.append({k: r[k] for k in ("key", "source", "current", "issues")})
    dump = lambda value: (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return {
        data["locale"] + ".json": dump(result),
        "repair-queue.json": dump({"locale": data["locale"], "tasks": queue}),
    }
