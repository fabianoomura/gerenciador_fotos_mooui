import type { Metadata } from "next";
import { Jost } from "next/font/google";
import "./globals.css";

const brandLogo = process.env.NEXT_PUBLIC_CATALOGO_LOGO_URL ?? "/catalog-icon.svg";

const jost = Jost({
  subsets: ["latin"],
  variable: "--font-catalogo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Catálogo Visual",
  description: "Catálogo local para pesquisa semântica e visual de fotografias",
  icons: {
    icon: brandLogo,
    shortcut: brandLogo,
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className={jost.variable}>{children}</body>
    </html>
  );
}
