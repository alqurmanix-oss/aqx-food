"""Conservative structured parser for AQX Blogger recipe HTML."""
import html
import re
from html.parser import HTMLParser

VERSION = "aqx-html-structured-v2"
INGREDIENT_LIST_CLASSES = {
    "aqx-ing-list", "aqx-ingredients-list", "aqx-ingredient-list",
}
INGREDIENT_NAME_CLASSES = {
    "aqx-ing-name", "aqx-ingredient-name", "aqx-ing-title",
}
INGREDIENT_QUANTITY_CLASSES = {
    "aqx-ing-qty", "aqx-ing-amount", "aqx-ingredient-amount",
}
DECORATIVE_INGREDIENT_CLASSES = {"aqx-check-icon", "aqx-ing-dot"}


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"\\s+", " ", value)
    return value.strip(" \\t\\r\\n•·-–—")


class RecipeHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.current_li = None
        self.current_step = None
        self.capture = None
        self.capture_parts = []
        self.capture_depth = None
        self.ingredients = []
        self.steps = []
        self.heading = None
        self.sections = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        self.stack.append((tag, classes))

        ancestor_classes = set().union(*(entry[1] for entry in self.stack[:-1])) if len(self.stack) > 1 else set()
        if tag == "li" and ancestor_classes.intersection(INGREDIENT_LIST_CLASSES):
            self.current_li = {"name": "", "quantity": "", "fallback_parts": []}

        if "aqx-step-card" in classes:
            self.current_step = {"title": "", "text": ""}

        if self.current_li is not None and classes.intersection(
            INGREDIENT_NAME_CLASSES | INGREDIENT_QUANTITY_CLASSES
        ):
            self.capture = (
                "name" if classes.intersection(INGREDIENT_NAME_CLASSES) else "quantity"
            )
            self.capture_parts = []
            self.capture_depth = len(self.stack)

        if self.current_step is not None and tag in {"h4", "p"}:
            self.capture = "step_title" if tag == "h4" else "step_text"
            self.capture_parts = []
            self.capture_depth = len(self.stack)

        if tag in {"h2", "h3"}:
            self.heading = {"text": [], "tag": tag}

    def handle_data(self, data):
        if self.current_li is not None:
            active_classes = set().union(*(entry[1] for entry in self.stack)) if self.stack else set()
            if not active_classes.intersection(DECORATIVE_INGREDIENT_CLASSES):
                self.current_li["fallback_parts"].append(data)

        if self.capture:
            self.capture_parts.append(data)
        if self.heading is not None:
            self.heading["text"].append(data)

    def handle_endtag(self, tag):
        if self.capture and self.capture_depth == len(self.stack):
            value = clean(" ".join(self.capture_parts))
            if self.current_li is not None and self.capture in {"name", "quantity"}:
                if value:
                    self.current_li[self.capture] = clean(
                        self.current_li[self.capture] + " " + value
                    )
                self.capture = None
                self.capture_parts = []
                self.capture_depth = None
            elif self.current_step is not None and self.capture in {"step_title", "step_text"}:
                key = "title" if self.capture == "step_title" else "text"
                if value:
                    self.current_step[key] = value
                self.capture = None
                self.capture_parts = []
                self.capture_depth = None

        if tag == "li" and self.current_li is not None:
            name = clean(self.current_li["name"])
            quantity = clean(self.current_li["quantity"])
            if not name:
                # Older AQX templates put ingredient text directly inside li,
                # often beside a decorative check icon, without name/amount spans.
                name = clean(" ".join(self.current_li["fallback_parts"]))
            if name:
                raw_line = clean(name + (" " + quantity if quantity else ""))
                self.ingredients.append({
                    "position": len(self.ingredients) + 1,
                    "raw_line": raw_line,
                    "raw_name": name,
                    "name_candidate": name,
                    "raw_quantity": quantity or None,
                    "contains_multiple": bool(re.search(r"\\s(?:و|مع)\\s", name)),
                    "contains_alternative": bool(re.search(r"\\bأو\\b|/|\\bor\\b", name, re.I)),
                    "extraction_method": "aqx_html_structured",
                })
            self.current_li = None

        if tag == "div" and self.current_step is not None:
            if self.stack and "aqx-step-card" in self.stack[-1][1]:
                self.steps.append(self.current_step)
                self.current_step = None

        if tag in {"h2", "h3"} and self.heading is not None:
            label = clean(" ".join(self.heading["text"]))
            if label:
                self.sections.append(label)
            self.heading = None

        if self.stack:
            self.stack.pop()


def parse_recipe_html(raw_html, title, source_url):
    parser = RecipeHTMLParser()
    parser.feed(raw_html or "")
    ingredients = parser.ingredients
    steps = parser.steps

    validation = []
    if not ingredients:
        validation.append("ingredients_not_extracted_from_structured_markup")
    if not steps:
        validation.append("preparation_steps_not_extracted_from_structured_markup")

    return {
        "external_record_id": None,
        "parsed_recipe": {
            "title": title,
            "source": "AQX Blogger",
            "source_url": source_url,
            "ingredients": ingredients,
            "ingredient_count": len(ingredients),
            "preparation_steps": [
                {"position": i + 1, "title": step["title"], "text": step["text"]}
                for i, step in enumerate(steps)
                if step.get("text")
            ],
            "preparation_step_count": len([s for s in steps if s.get("text")]),
            "review_required": True,
            "ingredient_extraction_method": "aqx_html_structured",
            "nutrition_values_from_blog_ignored": True,
        },
        "validation_errors": validation,
        "parse_status": "needs_review",
        "parser_version": VERSION,
    }
