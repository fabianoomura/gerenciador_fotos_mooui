import type { Metadata } from "next";
import { Jost } from "next/font/google";
import "./globals.css";

const jost = Jost({
  subsets: ["latin"],
  variable: "--font-catalogo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Catálogo Visual",
  description: "Catálogo local para pesquisa semântica e visual de fotografias",
  icons: {
    icon: "/catalog-icon.svg",
    shortcut: "/catalog-icon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className={jost.variable}>{children}</body>
    </html>
  );
}
