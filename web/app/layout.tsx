import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Goon - Your AI that does the thing so you don't have to",
  description:
    "Text or call one number. Goon answers questions, calls businesses, makes reservations, and remembers your preferences. No app needed.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">{children}</body>
    </html>
  );
}
