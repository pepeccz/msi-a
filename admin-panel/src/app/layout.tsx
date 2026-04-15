import type { Metadata } from "next";
import { DM_Sans, DM_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/auth-context";
import { SidebarProvider } from "@/contexts/sidebar-context";
import { SileoToaster } from "@/components/sileo-toaster";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
  weight: ["400", "500", "600", "700"],
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "MSI-a Admin Panel",
  description: "Panel de administracion para MSI Automotive",
  icons: {
    icon: "/logo.png",
    apple: "/logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* FOUC prevention: apply theme before first paint */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var t=localStorage.getItem("msi-admin-theme");if(t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme:dark)").matches)){document.documentElement.classList.add("dark")}})()`,
          }}
        />
      </head>
      <body className={`${dmSans.variable} ${dmMono.variable} font-sans`}>
        <AuthProvider>
          <SidebarProvider>{children}</SidebarProvider>
        </AuthProvider>
        <SileoToaster />
      </body>
    </html>
  );
}
