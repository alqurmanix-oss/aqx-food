import unittest
from aqx_food_recipe_parser import parse_recipe_html

class RecipeParserTests(unittest.TestCase):
    def test_extracts_ingredient_name_quantity_and_steps(self):
        html = """
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
        result = parse_recipe_html(html, "اختبار وصفة", "https://aqxfood.blogspot.com/test")
        recipe = result["parsed_recipe"]
        self.assertEqual(len(recipe["ingredients"]), 2)
        self.assertIn("طماطم ناضجة", recipe["ingredients"][0]["raw_name"])
        self.assertEqual(recipe["ingredients"][0]["raw_quantity"], "4 حبات كبيرة")
        self.assertEqual(len(recipe["preparation_steps"]), 2)
        self.assertEqual(recipe["preparation_steps"][0]["title"], "تشويح البصل")

    def test_does_not_invent_missing_steps(self):
        result = parse_recipe_html(
            '<ul class="aqx-ing-list"><li><span class="aqx-ing-name">ملح</span></li></ul>',
            "وصفة بلا خطوات", "https://aqxfood.blogspot.com/test"
        )
        self.assertEqual(result["parsed_recipe"]["preparation_steps"], [])
        self.assertIn("preparation_steps_not_extracted_from_structured_markup", result["validation_errors"])

if __name__ == "__main__":
    unittest.main()
