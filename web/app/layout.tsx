import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hold Plz - we make the calls you don't want to",
  description:
    "Text us what you need. We call the place. You get a text back when it's done. Restaurants, salons, dentists, vets, whatever.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link
          href="https://api.fontshare.com/v2/css?f[]=general-sans@400,500,600,700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
