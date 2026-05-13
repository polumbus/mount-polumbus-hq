import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { marketingLinks } from "@/lib/navigation";

export function MarketingNav() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/8 bg-[#08101D]/78 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
        <BrandMark />
        <nav className="hidden items-center gap-2 rounded-full border border-white/8 bg-white/[0.03] px-2 py-2 text-sm text-[#9AB2CC] md:flex">
          {marketingLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-full px-4 py-2 transition hover:bg-white/[0.04] hover:text-[#E8FAFF]"
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <Link
            href="/app"
            className="rounded-full border border-white/10 px-4 py-2 text-sm text-[#DCEAF6] transition hover:border-[#2DD4BF]/50 hover:bg-white/[0.03] hover:text-white"
          >
            Sign in
          </Link>
          <Link
            href="/app/onboarding"
            className="rounded-full bg-[linear-gradient(135deg,#00C8E8_0%,#00F5FF_55%,#7DFAFF_100%)] px-5 py-2.5 text-sm font-semibold uppercase tracking-[0.16em] text-[#051019] shadow-[0_0_30px_rgba(45,212,191,0.2)] transition hover:brightness-110"
          >
            Start setup
          </Link>
        </div>
      </div>
    </header>
  );
}
