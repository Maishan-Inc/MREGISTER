import "./globals.css";

export const metadata = {
  title: "MREGISTER",
  description: "MREGISTER Next.js console",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
