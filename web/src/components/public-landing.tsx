import Link from "next/link";

import { CheckoutButton } from "@/components/checkout-button";
import { MarketingNav } from "@/components/marketing-nav";
import { getBillingConfigStatus, isCheckoutPlanSlug } from "@/lib/billing";
import {
  getPublicPricingPackages,
} from "@/lib/scale-readiness";

const outcomes = [
  {
    label: "Write",
    title: "Turn rough ideas into posts that still sound human.",
    detail:
      "Creator Studio, Raw Thoughts, and Article Writer move from messy input to polished options without flattening your voice.",
  },
  {
    label: "Engage",
    title: "Make replies and research part of the same habit.",
    detail:
      "Reply Mode, Profile Analyzer, and Idea Bank keep daily interaction tied to your actual positioning.",
  },
  {
    label: "Learn",
    title: "Use your history instead of starting over every morning.",
    detail:
      "Post history, account audits, and reusable voice references make the workspace smarter as your archive grows.",
  },
];

const proofPoints = [
  "Creator Evolution keeps drafts close to your actual voice",
  "Pulse and signals turn what is happening now into usable angles",
  "Grades, history, and review loops make the system sharper over time",
];

export function PublicLanding() {
  const packages = getPublicPricingPackages();
  const billingConfig = getBillingConfigStatus();

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#07101A] text-white">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_18%_5%,rgba(45,212,191,0.20),transparent_30%),radial-gradient(circle_at_88%_12%,rgba(196,158,60,0.18),transparent_26%),linear-gradient(180deg,#0A1423_0%,#05070C_48%,#07101A_100%)]" />
      <MarketingNav />

      <main>
        <section className="relative mx-auto grid max-w-7xl gap-12 px-6 pb-20 pt-16 lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] lg:items-center lg:pb-28 lg:pt-24">
          <div>
            <p className="font-display text-lg uppercase tracking-[0.36em] text-[#2DD4BF]">
              Post Ascend
            </p>
            <h1 className="mt-6 max-w-5xl font-display text-6xl uppercase leading-[0.88] tracking-[0.055em] text-[#F4FAFF] sm:text-7xl lg:text-8xl">
              A creator operating system for posts that still sound like you.
            </h1>
            <p className="mt-7 max-w-3xl text-lg leading-8 text-[#A9BED6]">
              Build posts, replies, research, audits, and repeatable content habits from one
              workspace. Post Ascend turns your ideas, account context, and live signals into
              sharper publishing without sanding off your voice.
            </p>

            <div className="mt-9 flex flex-wrap gap-4">
              <Link
                href="/app/onboarding"
                className="rounded-full bg-[linear-gradient(135deg,#00C8E8_0%,#00F5FF_55%,#7DFAFF_100%)] px-7 py-3.5 text-sm font-semibold uppercase tracking-[0.2em] text-[#07111C] shadow-[0_0_42px_rgba(45,212,191,0.22)] transition hover:brightness-110"
              >
                Start workspace setup
              </Link>
              <Link
                href="/app/creator-studio"
                className="rounded-full border border-white/14 bg-white/[0.035] px-7 py-3.5 text-sm font-semibold uppercase tracking-[0.2em] text-[#EAF4FF] transition hover:border-[#C49E3C]/50 hover:bg-white/[0.06]"
              >
                Open the app
              </Link>
            </div>

            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              <div className="rounded-[28px] border border-white/10 bg-white/[0.045] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[#7B96B7]">Voice</p>
                <p className="mt-3 text-3xl font-semibold text-[#F4FAFF]">Yours</p>
                <p className="mt-1 text-sm text-[#9DB4CD]">calibrated from your archive</p>
              </div>
              <div className="rounded-[28px] border border-white/10 bg-white/[0.045] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[#7B96B7]">Signals</p>
                <p className="mt-3 text-3xl font-semibold text-[#F4FAFF]">Live</p>
                <p className="mt-1 text-sm text-[#9DB4CD]">turn topics into drafts</p>
              </div>
              <div className="rounded-[28px] border border-white/10 bg-white/[0.045] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-[#7B96B7]">Workflow</p>
                <p className="mt-3 text-3xl font-semibold text-[#F4FAFF]">Daily</p>
                <p className="mt-1 text-sm text-[#9DB4CD]">create, grade, publish, learn</p>
              </div>
            </div>
          </div>

          <aside className="relative">
            <div className="absolute -inset-6 rounded-[48px] bg-[radial-gradient(circle_at_50%_0%,rgba(45,212,191,0.22),transparent_55%)] blur-2xl" />
            <div className="relative overflow-hidden rounded-[42px] border border-white/12 bg-[linear-gradient(180deg,rgba(13,30,54,0.94),rgba(6,11,19,0.98))] p-6 shadow-[0_40px_140px_rgba(0,0,0,0.45)]">
              <div className="rounded-[32px] border border-white/10 bg-[#07111E] p-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-display text-sm uppercase tracking-[0.3em] text-[#C49E3C]">
                      Today
                    </p>
                    <h2 className="mt-2 text-2xl font-semibold text-[#F4FAFF]">
                      One sharper publishing loop
                    </h2>
                  </div>
                  <span className="rounded-full border border-[#2DD4BF]/30 bg-[#0E2B35] px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-[#7FE5D6]">
                    Preview
                  </span>
                </div>

                <div className="mt-6 space-y-3">
                  {["Find the signal", "Shape the draft", "Grade the post", "Save the lesson"].map(
                    (item, index) => (
                      <div
                        key={item}
                        className="grid grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 rounded-[22px] border border-white/8 bg-white/[0.04] p-3"
                      >
                        <span className="grid h-9 w-9 place-items-center rounded-full bg-[#10273A] text-sm font-semibold text-[#7FE5D6]">
                          {index + 1}
                        </span>
                        <span className="text-sm font-semibold text-[#EAF4FF]">{item}</span>
                        <span className="h-2 w-2 rounded-full bg-[#2DD4BF]" />
                      </div>
                    ),
                  )}
                </div>
              </div>

              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <div className="rounded-[28px] border border-[#2DD4BF]/18 bg-[#0E2330]/70 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[#70D9CF]">
                    Creator Evolution
                  </p>
                  <p className="mt-3 text-2xl font-semibold text-[#F4FAFF]">voice-aware</p>
                  <p className="mt-2 text-sm leading-6 text-[#9DB4CD]">
                    Drafts use your approved voice, format, and learning rules.
                  </p>
                </div>
                <div className="rounded-[28px] border border-[#C49E3C]/20 bg-[#20180E]/70 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[#F0D695]">
                    Pulse
                  </p>
                  <p className="mt-3 text-2xl font-semibold text-[#F4FAFF]">live topics</p>
                  <p className="mt-2 text-sm leading-6 text-[#CBBE9C]">
                    Turn what people are discussing right now into timely posts.
                  </p>
                </div>
              </div>
            </div>
          </aside>
        </section>

        <section id="features" className="mx-auto max-w-7xl px-6 py-16">
          <div className="max-w-3xl">
            <p className="font-display text-base uppercase tracking-[0.34em] text-[#2DD4BF]">
              Product
            </p>
              <h2 className="mt-4 text-4xl font-semibold text-[#F4FAFF] sm:text-5xl">
              The product is built around one promise: publish faster without sounding generic.
              </h2>
          </div>
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {outcomes.map((outcome) => (
              <article
                key={outcome.label}
                className="rounded-[34px] border border-white/10 bg-white/[0.045] p-7 shadow-[0_24px_80px_rgba(0,0,0,0.22)]"
              >
                <p className="font-display text-sm uppercase tracking-[0.32em] text-[#C49E3C]">
                  {outcome.label}
                </p>
                <h3 className="mt-4 text-2xl font-semibold text-[#F4FAFF]">{outcome.title}</h3>
                <p className="mt-4 text-sm leading-7 text-[#9EB4CC]">{outcome.detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-7xl px-6 py-16">
          <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
            <div className="max-w-3xl">
              <p className="font-display text-base uppercase tracking-[0.34em] text-[#C49E3C]">
                Pricing
              </p>
              <h2 className="mt-4 text-4xl font-semibold text-[#F4FAFF] sm:text-5xl">
                Clear packaging with simple workspace setup.
              </h2>
              <p className="mt-4 text-base leading-8 text-[#A9BED6]">
                Creator and Growth plans start through the setup flow. Operator stays
                application-based so managed workflows can be scoped before payment.
              </p>
            </div>
            <Link
              href="/app"
              className="inline-flex w-fit rounded-full border border-[#2DD4BF]/30 px-6 py-3 text-sm font-semibold uppercase tracking-[0.2em] text-[#DFFBFF] transition hover:bg-[#0E2B35]"
            >
              Request access
            </Link>
          </div>

          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {packages.map((plan) => (
              <article
                key={plan.slug}
                className="relative rounded-[36px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.025))] p-7 shadow-[0_24px_90px_rgba(0,0,0,0.24)]"
              >
                {plan.badge ? (
                  <span className="absolute right-6 top-6 rounded-full bg-[#2DD4BF] px-3 py-1 text-xs font-bold uppercase tracking-[0.2em] text-[#06111B]">
                    {plan.badge}
                  </span>
                ) : null}
                <p className="font-display text-sm uppercase tracking-[0.3em] text-[#7FE5D6]">
                  {plan.name}
                </p>
                <div className="mt-5 flex items-end gap-2">
                  <p className="text-5xl font-semibold text-[#F4FAFF]">{plan.price}</p>
                  <p className="pb-1 text-sm text-[#9DB4CD]">{plan.cadence}</p>
                </div>
                <p className="mt-5 text-sm leading-7 text-[#A9BED6]">{plan.summary}</p>
                <ul className="mt-6 space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-3 text-sm leading-6 text-[#DCEAF6]">
                      <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#2DD4BF]" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                {isCheckoutPlanSlug(plan.slug) ? (
                  billingConfig.checkoutReady ? (
                    <CheckoutButton planSlug={plan.slug} label={plan.primaryCta} />
                  ) : (
                    <Link
                      href={`/app/onboarding?plan=${plan.slug}`}
                      className="mt-7 inline-flex rounded-full bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-[#07111C] transition hover:bg-[#DFFBFF]"
                    >
                      {plan.primaryCta}
                    </Link>
                  )
                ) : (
                  <Link
                    href="/app/onboarding?plan=operator"
                    className="mt-7 inline-flex rounded-full bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-[#07111C] transition hover:bg-[#DFFBFF]"
                  >
                    {plan.primaryCta}
                  </Link>
                )}
              </article>
            ))}
          </div>
        </section>

        <section id="workflow" className="mx-auto max-w-7xl px-6 py-16">
          <div className="rounded-[42px] border border-white/10 bg-[linear-gradient(135deg,rgba(13,30,54,0.86),rgba(7,12,22,0.96))] p-7 shadow-[0_30px_120px_rgba(0,0,0,0.3)] lg:p-10">
            <div className="grid gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(420px,1.1fr)]">
              <div>
                <p className="font-display text-base uppercase tracking-[0.34em] text-[#2DD4BF]">
                  Workflow
                </p>
                <h2 className="mt-4 text-4xl font-semibold text-[#F4FAFF]">
                  The workspace keeps the loop tight from idea to published post.
                </h2>
                <p className="mt-5 text-base leading-8 text-[#A9BED6]">
                  Start with an angle, pull in the right context, generate options, grade the
                  result, and keep the useful learning attached to the next draft.
                </p>
                <div className="mt-7 flex flex-wrap gap-3">
                  {proofPoints.map((point) => (
                    <span
                      key={point}
                      className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-[#DCEAF6]"
                    >
                      {point}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid gap-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    {
                      label: "Creator Evolution",
                      detail: "Builds posts from your concept using approved voice and format rules.",
                    },
                    {
                      label: "What is hot",
                      detail: "Turns current signals into timely ideas without losing your point of view.",
                    },
                    {
                      label: "Grades",
                      detail: "Shows what is working, what is weak, and the exact segment to improve.",
                    },
                    {
                      label: "History",
                      detail: "Keeps prior posts and approved edits available as voice calibration.",
                    },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="rounded-[28px] border border-white/10 bg-white/[0.045] p-5"
                    >
                      <span className="rounded-full bg-[#143A32] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#7FE5D6]">
                        included
                      </span>
                      <p className="mt-4 text-lg font-semibold text-[#F4FAFF]">{item.label}</p>
                      <p className="mt-2 text-sm leading-6 text-[#9EB4CC]">{item.detail}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-[30px] border border-white/10 bg-[#07111E] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[#7B96B7]">
                    Daily operating loop
                  </p>
                  <div className="mt-4 grid gap-3">
                    {[
                      ["Capture", "Drop in the raw thought, link, topic, or signal."],
                      ["Generate", "Get distinct options in the selected voice and format."],
                      ["Decide", "Use grades and review notes to pick the strongest version."],
                      ["Learn", "Save what worked so the next draft starts smarter."],
                    ].map(([label, detail]) => (
                      <div
                        key={label}
                        className="grid gap-2 rounded-[22px] border border-white/8 bg-white/[0.035] p-4 sm:grid-cols-[minmax(0,1fr)_auto]"
                      >
                        <div>
                          <p className="text-sm font-semibold text-[#EAF4FF]">{label}</p>
                          <p className="mt-1 text-xs text-[#8DA4C0]">{detail}</p>
                        </div>
                        <p className="text-sm font-semibold text-[#7FE5D6]">step</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="preview" className="mx-auto max-w-7xl px-6 py-16 pb-24">
          <div className="rounded-[42px] border border-[#2DD4BF]/18 bg-[#0E2330]/75 p-8 text-center shadow-[0_30px_120px_rgba(0,0,0,0.25)]">
            <p className="font-display text-base uppercase tracking-[0.34em] text-[#7FE5D6]">
              Want to inspect the product first?
            </p>
            <h2 className="mx-auto mt-4 max-w-3xl text-4xl font-semibold text-[#F4FAFF]">
              Open the preserved Streamlit-style app preview without entering the signup flow.
            </h2>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Link
                href="/app/creator-studio"
                className="rounded-full bg-[#F4FAFF] px-7 py-3.5 text-sm font-semibold uppercase tracking-[0.2em] text-[#07111C] transition hover:bg-[#DFFBFF]"
              >
                Open app
              </Link>
              <Link
                href="/app/onboarding"
                className="rounded-full border border-white/14 px-7 py-3.5 text-sm font-semibold uppercase tracking-[0.2em] text-[#EAF4FF] transition hover:bg-white/[0.06]"
              >
                Start signup
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
