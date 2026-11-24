"""Conservative parser for AQX Blogger recipe HTML."""
import html
import re
from html.parser import HTMLParser

VERSION = "aqx-html-structured-v6"
INGREDIENT_LIST_CLASSES = {
    "aqx-ing-list", "aqx-ingredients-list", "aqx-ingredient-list",
}
INGREDIENT_NAME_CLASSES = {
    "aqx-ing-name", "aqx-ingredient-name", "aqx-ing-title",
}
INGREDIENT_QUANTITY_CLASSES = {
    "aqx-ing-qty", "aqx-ing-amount", "aqx-ingredient-amount",
}
DECORATIVE_CLASSES = {"aqx-check-icon", "aqx-ing-dot", "aqx-step-badge"}
METHOD_HEADING_RE = re.compile(
    r"(طريقة\s*(?:التحضير|تحضير|عمل)|خطوات\s*(?:التحضير|العمل)|"
    r"preparation|instructions|method)", re.I
)
INGREDIENT_HEADING_RE = re.compile(r"(المكونات|المقادير|ingredients)", re.I)
NON_METHOD_HEADING_RE = re.compile(r"(نصائح|ملاحظات|التقديم|القيم الغذائية|nutrition|tips)", re.I)


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n•·-–—🔹")


class RecipeHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.current_li = None
        self.current_step_card = None
        self.capture = None
        self.capture_parts = []
        self.capture_depth = None
        self.ingredients = []
        self.steps = []
        self.heading = None
        self.method_context = False
        self.pending_step_title = ""
        self.method_li = None
        self.method_li_depth = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        ancestors = set().union(*(entry[1] for entry in self.stack)) if self.stack else set()
        self.stack.append((tag, classes))

        if tag == "li" and ancestors.intersection(INGREDIENT_LIST_CLASSES):
            self.current_li = {"name": "", "quantity": "", "fallback_parts": []}

        if classes.intersection({"aqx-step-card", "aqx-step-item"}):
            self.current_step_card = {"title": "", "text": ""}

        if self.current_li is not None and classes.intersection(
            INGREDIENT_NAME_CLASSES | INGREDIENT_QUANTITY_CLASSES
        ):
            self.capture = "name" if classes.intersection(INGREDIENT_NAME_CLASSES) else "quantity"
            self.capture_parts = []
            self.capture_depth = len(self.stack)

        if self.current_step_card is not None and (
            tag in {"h4", "p"} or classes.intersection({"aqx-step-title", "aqx-step-text"})
        ):
            self.capture = (
                "step_title" if tag == "h4" or "aqx-step-title" in classes else "step_text"
            )
            self.capture_parts = []
            self.capture_depth = len(self.stack)

        if tag == "li" and self.method_context and not ancestors.intersection(INGREDIENT_LIST_CLASSES):
            self.method_li = []
            self.method_li_depth = len(self.stack)

        if tag in {"h2", "h3", "h4"} or classes.intersection({"aqx-h2", "aqx-h3"}):
            self.heading = {"text": [], "tag": tag, "depth": len(self.stack)}

    def handle_data(self, data):
        if self.current_li is not None:
            active_classes = set().union(*(entry[1] for entry in self.stack)) if self.stack else set()
            if not active_classes.intersection(DECORATIVE_CLASSES):
                self.current_li["fallback_parts"].append(data)

        if self.capture:
            self.capture_parts.append(data)

        if self.method_li is not None:
            active_classes = set().union(*(entry[1] for entry in self.stack)) if self.stack else set()
            if not active_classes.intersection(DECORATIVE_CLASSES):
                self.method_li.append(data)

        if self.heading is not None:
            self.heading["text"].append(data)

    def _finish_heading(self):
        label = clean(" ".join(self.heading["text"])) if self.heading else ""
        if not label:
            return
        if METHOD_HEADING_RE.search(label) or re.search(r"^(?:الخطوة|خطوة)\\s", label):
            self.method_context = True
            self.pending_step_title = label
        elif INGREDIENT_HEADING_RE.search(label) or NON_METHOD_HEADING_RE.search(label):
            self.method_context = False
            self.pending_step_title = ""
        elif self.method_context and self.heading["tag"] in {"h3", "h4"}:
            self.pending_step_title = label

    def handle_endtag(self, tag):
        if self.capture and self.capture_depth == len(self.stack):
            value = clean(" ".join(self.capture_parts))
            if self.current_li is not None and self.capture in {"name", "quantity"}:
                if value:
                    self.current_li[self.capture] = clean(self.current_li[self.capture] + " " + value)
            elif self.current_step_card is not None and self.capture in {"step_title", "step_text"}:
                key = "title" if self.capture == "step_title" else "text"
                if value:
                    self.current_step_card[key] = value
            self.capture = None
            self.capture_parts = []
            self.capture_depth = None

        if tag == "li" and self.current_li is not None:
            name = clean(self.current_li["name"]) or clean(" ".join(self.current_li["fallback_parts"]))
            quantity = clean(self.current_li["quantity"])
            if name:
                self.ingredients.append({
                    "position": len(self.ingredients) + 1,
                    "raw_line": clean(name + (" " + quantity if quantity else "")),
                    "raw_name": name,
                    "name_candidate": name,
                    "raw_quantity": quantity or None,
                    "contains_multiple": bool(re.search(r"\s(?:و|مع)\s", name)),
                    "contains_alternative": bool(re.search(r"\bأو\b|/|\bor\b", name, re.I)),
                    "extraction_method": "aqx_html_structured",
                })
            self.current_li = None

        if tag == "li" and self.method_li is not None:
            text = clean(" ".join(self.method_li))
            if text:
                self.steps.append({
                    "title": self.pending_step_title,
                    "text": text,
                    "extraction_method": "aqx_method_section_list",
                })
            self.method_li = None
            self.method_li_depth = None

        if tag == "div" and self.current_step_card is not None:
            if self.stack and self.stack[-1][1].intersection({"aqx-step-card", "aqx-step-item"}):
                if self.current_step_card.get("text"):
                    self.steps.append({
                        **self.current_step_card,
                        "extraction_method": "aqx_step_card" if "aqx-step-card" in self.stack[-1][1] else "aqx_step_item",
                    })
                self.current_step_card = None

        if self.heading is not None and self.heading.get("depth") == len(self.stack):
            self._finish_heading()
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

    clean_steps = [
        {"position": i + 1, "title": step.get("title") or None, "text": step["text"]}
        for i, step in enumerate(steps) if step.get("text")
    ]
    return {
        "external_record_id": None,
        "parsed_recipe": {
            "title": title,
            "source": "AQX Blogger",
            "source_url": source_url,
            "ingredients": ingredients,
            "ingredient_count": len(ingredients),
            "preparation_steps": clean_steps,
            "preparation_step_count": len(clean_steps),
            "review_required": True,
            "ingredient_extraction_method": "aqx_html_structured",
            "nutrition_values_from_blog_ignored": True,
        },
        "validation_errors": validation,
        "parse_status": "needs_review",
        "parser_version": VERSION,
    }
