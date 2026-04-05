import { IBM_Plex_Sans, Rubik } from "next/font/google";
import "./globals.css";

const bodyFont = IBM_Plex_Sans({
  subsets: ["latin", "cyrillic"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

const displayFont = Rubik({
  subsets: ["latin", "cyrillic"],
  variable: "--font-display",
  weight: ["400", "500", "700", "800"],
});

export const metadata = {
  title: "Портал поставщиков",
  description: "Клиентский сайт для поиска и подбора товаров на базе Smart Search API.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body className={`${bodyFont.variable} ${displayFont.variable}`}>{children}</body>
    </html>
  );
}
