"""The demo catalogue: invented products in the style of a small Caribbean shop.

Prices are VAT-inclusive, in cents. Basic foods are zero-rated for VAT.
"""

CATEGORIES = ["Pantry", "Crafts", "Bath & Body", "Tea & Cocoa"]

#  sku, name, category, price (cents), VAT %, stock, description
PRODUCTS = [
    ("PN-NUT", "Whole Nutmeg, 100g", "Pantry", 850, 0, 40, "Whole nutmegs with the mace still on. Grate fresh over punch, porridge or cake."),
    ("PN-ARR", "Arrowroot Starch, 500g", "Pantry", 950, 0, 25, "Fine arrowroot starch for thickening sauces and baking."),
    ("PN-HOT", "Scotch Bonnet Hot Sauce", "Pantry", 1160, 16, 60, "Fiery and fruity, with scotch bonnet peppers, mango and lime."),
    ("PN-GUA", "Guava Jam", "Pantry", 1450, 16, 18, "Slow-cooked guava jam. Lovely on bakes and in tarts."),
    ("PN-SOR", "Sorrel Syrup", "Pantry", 1800, 16, 4, "Concentrated sorrel with ginger and clove. Mix one part to four parts water."),
    ("PN-BRF", "Breadfruit Chips", "Pantry", 650, 16, 35, "Thin, crisp breadfruit chips with sea salt."),
    ("PN-CAK", "Spiced Rum Cake", "Pantry", 3500, 16, 12, "A dense, dark fruit cake soaked in spiced syrup. Serves eight."),
    ("CR-BSK", "Woven Palm Basket", "Crafts", 7500, 16, 3, "Hand-woven from dried palm leaves. About 30cm across."),
    ("CR-BWL", "Hand-carved Mahogany Bowl", "Crafts", 9500, 16, 6, "Turned and finished by hand. Every bowl is slightly different."),
    ("CR-SCF", "Batik Scarf", "Crafts", 6500, 16, 9, "Cotton scarf, hand-dyed using the batik wax method."),
    ("CR-EAR", "Coconut Shell Earrings", "Crafts", 4200, 16, 14, "Light earrings cut and polished from coconut shell."),
    ("BB-SOP", "Coconut Oil Soap", "Bath & Body", 1500, 16, 45, "Cold-process soap with virgin coconut oil."),
    ("BB-ALO", "Aloe Vera Gel", "Bath & Body", 2200, 16, 2, "Soothing gel from home-grown aloe."),
    ("BB-BAY", "Bay Rum Aftershave", "Bath & Body", 2800, 16, 11, "The classic bay leaf and spice aftershave."),
    ("TC-LEM", "Lemongrass Tea, 40g", "Tea & Cocoa", 1300, 16, 30, "Dried lemongrass for a calming hot or iced tea."),
    ("TC-COC", "Cocoa Tea Balls, pack of 6", "Tea & Cocoa", 1200, 16, 22, "Grated cocoa with cinnamon and nutmeg. Boil one ball in milk."),
    ("TC-NIB", "Roasted Cocoa Nibs, 200g", "Tea & Cocoa", 1900, 16, 0, "Crunchy roasted nibs for baking or snacking."),
]
