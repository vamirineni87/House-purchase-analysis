import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PIPA — Property Intelligence Platform",
  description: "County-backed property research for Fairfax and Loudoun County, VA",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <aside className="w-64 bg-white border-r border-gray-200 p-4 hidden md:block">
            <h1 className="text-xl font-bold mb-6">PIPA</h1>
            <nav className="space-y-2">
              <a href="/" className="block px-3 py-2 rounded-md hover:bg-gray-100 font-medium">
                Dashboard
              </a>
              <a href="/properties" className="block px-3 py-2 rounded-md hover:bg-gray-100">
                Properties
              </a>
              <a href="/comparison" className="block px-3 py-2 rounded-md hover:bg-gray-100">
                Compare
              </a>
              <a href="/alerts" className="block px-3 py-2 rounded-md hover:bg-gray-100">
                Alerts
              </a>
              <a href="/settings" className="block px-3 py-2 rounded-md hover:bg-gray-100">
                Settings
              </a>
            </nav>
          </aside>

          {/* Main content */}
          <main className="flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
