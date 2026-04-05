const RULES = [
  {
    image: "/images/products/oil-industrial.svg",
    keywords: ["масла мотор", "масла транс", "масла гидр", "маслостан", "автомоб", "смаз", "компресс", "индустри"],
  },
  {
    image: "/images/products/food-oil.svg",
    keywords: ["масло слив", "масло подсол", "оливков", "кунжут", "пищев", "соусы", "рыбные", "шпроты", "семена маслич"],
  },
  {
    image: "/images/products/electronics.svg",
    keywords: ["ноутбук", "клавиат", "мыш", "монитор", "принтер", "сервер", "компьют", "диспле", "заряд"],
  },
  {
    image: "/images/products/medical.svg",
    keywords: ["перчат", "медицин", "шприц", "препарат", "фарма", "кожи", "лекар", "стомат", "хирург"],
  },
  {
    image: "/images/products/office.svg",
    keywords: ["бумаг", "канцел", "ручк", "маркер", "тетрад", "учебник", "офис", "документ"],
  },
  {
    image: "/images/products/cleaning.svg",
    keywords: ["пылесос", "убор", "фильтр", "очист", "моющ", "хозяй", "салфет", "мыло"],
  },
];

function normalizeProductText(product) {
  return [product?.category, product?.title, product?.attributes?.raw]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function getProductImage(product) {
  const haystack = normalizeProductText(product);
  const match = RULES.find((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)));
  return match?.image || "/images/products/generic.svg";
}
