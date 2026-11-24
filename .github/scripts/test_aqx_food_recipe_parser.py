import unittest
from aqx_food_recipe_parser import parse_recipe_html


class RecipeParserTests(unittest.TestCase):
    def test_extracts_ingredient_name_quantity_and_steps(self):
        source_html = """
        <div class="aqx-ingredients-grid">
          <ul class="aqx-ing-list">
            <li><span class="aqx-ing-name"><span>🍅</span> طماطم ناضجة</span>
                <span class="aqx-ing-qty">4 حبات كبيرة</span></li>
            <li><span class="aqx-ing-name">ثوم مفروم</span>
                <span class="aqx-ing-qty">3 فصوص</span></li>
          </ul>
        </div>
        <div class="aqx-step-card"><div><h4>تشويح البصل</h4><p>سخّن الزيت ثم أضف البصل.</p></div></div>
        <div class="aqx-step-card"><div><h4>إضافة الطماطم</h4><p>أضف الطماطم واتركها تنضج.</p></div></div>
        """
        result = parse_recipe_html(source_html, "اختبار وصفة", "https://aqxfood.blogspot.com/test")
        recipe = result["parsed_recipe"]
        self.assertEqual(len(recipe["ingredients"]), 2)
        self.assertIn("طماطم ناضجة", recipe["ingredients"][0]["raw_name"])
        self.assertEqual(recipe["ingredients"][0]["raw_quantity"], "4 حبات كبيرة")
        self.assertEqual(len(recipe["preparation_steps"]), 2)
        self.assertEqual(recipe["preparation_steps"][0]["title"], "تشويح البصل")

    def test_extracts_legacy_plain_list_items(self):
        # Actual AQX template: ingredient text is direct li text, with a decorative icon.
        source_html = """
        <div class="aqx-ingredients-grid">
          <ul class="aqx-ing-list">
            <li><span class="aqx-check-icon">✓</span> 4 صدور دجاج كاملة ومخلية</li>
            <li><span class="aqx-check-icon">✓</span> 1 كوب لبن رائب (لتطرية الدجاج)</li>
            <li><span class="aqx-check-icon">✓</span> زيت قلي غزير</li>
          </ul>
        </div>
        """
        result = parse_recipe_html(source_html, "برجر دجاج كرسبي", "https://aqxfood.blogspot.com/test")
        ingredients = result["parsed_recipe"]["ingredients"]
        self.assertEqual(len(ingredients), 3)
        self.assertIn("صدور دجاج", ingredients[0]["raw_name"])
        self.assertNotIn("✓", ingredients[0]["raw_name"])

    def test_extracts_legacy_method_section_list_steps(self):
        source_html = """
        <h2>طريقة التحضير</h2>
        <div><h3>تجهيز التوابل والتتبيل</h3>
          <ul>
            <li>حمّصي التوابل في مقلاة جافة.</li>
            <li>أضيفي السمك والزبادي وقلّبي برفق.</li>
          </ul>
        </div>
        <h2>المقادير</h2>
        <ul class="aqx-ing-list"><li><span class="aqx-ing-name">سمك فيليه</span>
          <span class="aqx-ing-amount">500 غرام</span></li></ul>
        """
        result = parse_recipe_html(source_html, "برياني سمك", "https://aqxfood.blogspot.com/test")
        recipe = result["parsed_recipe"]
        self.assertEqual(len(recipe["preparation_steps"]), 2)
        self.assertIn("حمّصي التوابل", recipe["preparation_steps"][0]["text"])
        self.assertEqual(len(recipe["ingredients"]), 1)


    def test_extracts_method_steps_from_aqx_div_headings(self):
        source_html = """
        <div class="aqx-h2"><div class="aqx-h2-icon">🍳</div>
          <span>طريقة التحضير</span></div>
        <div class="aqx-h3">خطوة تجهيز التوابل والتتبيل</div>
        <ul><li>حمّصي التوابل في مقلاة جافة.</li>
            <li>أضيفي السمك وقلّبي برفق.</li></ul>
        <div class="aqx-h2"><span>مقادير الوصفة</span></div>
        <ul class="aqx-ing-list"><li><span class="aqx-ing-name">سمك فيليه</span>
          <span class="aqx-ing-amount">500 غرام</span></li></ul>
        """
        result = parse_recipe_html(source_html, "برياني سمك", "https://aqxfood.blogspot.com/test")
        recipe = result["parsed_recipe"]
        self.assertEqual(len(recipe["preparation_steps"]), 2)
        self.assertEqual(len(recipe["ingredients"]), 1)
        self.assertIn("حمّصي التوابل", recipe["preparation_steps"][0]["text"])


    def test_extracts_aqx_step_item_title_and_text(self):
        source_html = """
        <h2 class="aqx-h2">طريقة تحضير الوصفة</h2>
        <div class="aqx-steps-container">
          <div class="aqx-step-item">
            <div class="aqx-step-badge">1</div>
            <div class="aqx-step-title"><span>إذابة الزبدة</span></div>
            <p class="aqx-step-text">ذوّبي الزبدة في مقلاة على نار متوسطة.</p>
          </div>
          <div class="aqx-step-item">
            <div class="aqx-step-title">إضافة البصل</div>
            <p class="aqx-step-text">أضيفي البصل وقلّبي جيداً.</p>
          </div>
        </div>
        """
        result = parse_recipe_html(source_html, "تغميسة البصل", "https://aqxfood.blogspot.com/test")
        steps = result["parsed_recipe"]["preparation_steps"]
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["title"], "إذابة الزبدة")
        self.assertIn("ذوّبي الزبدة", steps[0]["text"])


    def test_extracts_div_ingredient_items_and_step_content(self):
        source_html = """
        <div class="aqx-card-wrapper">
          <h2>مقادير عجينة القطايف</h2>
          <div class="aqx-ingredients-grid">
            <div class="aqx-ingredient-item">
              <span class="aqx-ing-icon">🍚</span><span>دقيق: كوبان</span>
            </div>
            <div class="aqx-ingredient-item">
              <span class="aqx-ing-icon">🍬</span><span>سكر: ملعقتان كبيرتان</span>
            </div>
          </div>
        </div>
        <div class="aqx-card-wrapper">
          <h2>طريقة تحضير العجينة</h2>
          <div class="aqx-step-card">
            <div class="aqx-step-number">1</div>
            <div class="aqx-step-content"><strong>خلط المكونات:</strong> اخلطي المكونات جيداً.</div>
          </div>
        </div>
        """
        result = parse_recipe_html(source_html, "عجينة القطايف", "https://aqxfood.blogspot.com/test")
        recipe = result["parsed_recipe"]
        self.assertEqual(len(recipe["ingredients"]), 2)
        self.assertEqual(recipe["ingredients"][0]["raw_name"], "دقيق")
        self.assertEqual(recipe["ingredients"][0]["raw_quantity"], "كوبان")
        self.assertEqual(recipe["preparation_steps"][0]["title"], "خلط المكونات")
        self.assertIn("اخلطي المكونات", recipe["preparation_steps"][0]["text"])

    def test_does_not_invent_missing_steps(self):
        result = parse_recipe_html(
            '<ul class="aqx-ing-list"><li><span class="aqx-ing-name">ملح</span></li></ul>',
            "وصفة بلا خطوات", "https://aqxfood.blogspot.com/test"
        )
        self.assertEqual(result["parsed_recipe"]["preparation_steps"], [])
        self.assertIn(
            "preparation_steps_not_extracted_from_structured_markup",
            result["validation_errors"],
        )


if __name__ == "__main__":
    unittest.main()
