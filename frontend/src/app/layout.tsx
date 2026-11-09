import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Íris — Adaptação Inteligente de Materiais Pedagógicos",
  description:
    "Plataforma gratuita para professores adaptarem materiais e atividades pedagógicas com inteligência artificial baseada em evidências (DUA/MEC) e privacidade Zero-Database (LGPD).",
  icons: {
    icon: "/favicon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="min-h-screen bg-[#F5EDF0] text-[#0D0221] dark:bg-[#0D0221] dark:text-[#F5EDF0] transition-colors duration-200">
        <a
          href="#conteudo-principal"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[#E35336] focus:text-white focus:font-semibold"
        >
          Pular para o conteúdo principal
        </a>
        {children}
      </body>
    </html>
  );
}
