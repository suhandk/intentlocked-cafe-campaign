import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Intent Locked · Campaign workspace",
  description: "Human controls truth. AI controls execution. Code enforces the boundary.",
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
