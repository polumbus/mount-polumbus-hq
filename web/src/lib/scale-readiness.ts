export type PublicPlanSlug = "starter" | "growth" | "operator";

export type PublicPricingPackage = {
  slug: PublicPlanSlug;
  name: string;
  price: string;
  cadence: string;
  summary: string;
  primaryCta: string;
  features: string[];
  badge?: string;
};

export type RateLimitPolicy = {
  key: "publicLead" | "aiBuild" | "xRefresh" | "profileResearch";
  label: string;
  windowMs: number;
  maxRequests: number;
  costWeight: number;
  requiresAuth: boolean;
  ownerBypass: boolean;
};

export type ScaleReadinessCheckpoint = {
  label: string;
  status: "ready" | "next";
  detail: string;
};

export const initialCapacityTarget = {
  users: 500,
  activeWorkspacesPerMinute: 40,
  aiGenerationsPerMinute: 24,
};

export const publicPricingPackages: PublicPricingPackage[] = [
  {
    slug: "starter",
    name: "Creator",
    price: "$49",
    cadence: "per month",
    summary: "For creators who need a daily writing and reply system that feels like them.",
    primaryCta: "Start workspace setup",
    features: [
      "Creator Studio, Raw Thoughts, Reply Mode, and Idea Bank",
      "Account context, post history, and reusable voice references",
      "Practical daily limits designed to keep AI costs predictable",
    ],
  },
  {
    slug: "growth",
    name: "Growth",
    price: "$149",
    cadence: "per month",
    summary: "For serious operators who want strategy, research, and publishing momentum together.",
    primaryCta: "Request growth access",
    badge: "Best fit",
    features: [
      "Everything in Creator plus Profile Analyzer and Account Audit",
      "Higher AI-generation budget for drafting, grading, and research",
      "Priority onboarding review before high-volume posting",
    ],
  },
  {
    slug: "operator",
    name: "Operator",
    price: "Custom",
    cadence: "founding partner",
    summary: "For teams, athletes, founders, and media operators who need a managed content cockpit.",
    primaryCta: "Talk to us",
    features: [
      "Signals, Podcast, Gameday, and custom operator workflows",
      "Shared operating rules, custom workflow fit, and controlled rollouts",
      "Usage reviews before expanding seats or automation volume",
    ],
  },
];

export const scaleRateLimitPolicies: RateLimitPolicy[] = [
  {
    key: "publicLead",
    label: "Public lead/signup intent",
    windowMs: 60 * 60 * 1000,
    maxRequests: 6,
    costWeight: 1,
    requiresAuth: false,
    ownerBypass: false,
  },
  {
    key: "aiBuild",
    label: "AI draft/build actions",
    windowMs: 60 * 1000,
    maxRequests: 8,
    costWeight: 8,
    requiresAuth: true,
    ownerBypass: true,
  },
  {
    key: "xRefresh",
    label: "Live X refreshes",
    windowMs: 15 * 60 * 1000,
    maxRequests: 4,
    costWeight: 5,
    requiresAuth: true,
    ownerBypass: true,
  },
  {
    key: "profileResearch",
    label: "Profile research runs",
    windowMs: 60 * 60 * 1000,
    maxRequests: 12,
    costWeight: 10,
    requiresAuth: true,
    ownerBypass: true,
  },
];

export function getPublicPricingPackages() {
  return publicPricingPackages;
}

export function getRateLimitPolicy(key: RateLimitPolicy["key"]) {
  return scaleRateLimitPolicies.find((policy) => policy.key === key);
}

export function buildRateLimitKey(args: {
  policyKey: RateLimitPolicy["key"];
  userId?: string | null;
  ipAddress?: string | null;
}) {
  const subject = args.userId?.trim() || args.ipAddress?.trim() || "anonymous";
  return `pa:${args.policyKey}:${subject}`;
}

export function getScaleReadinessChecklist(): ScaleReadinessCheckpoint[] {
  return [
    {
      label: "500-user entry target",
      status: "ready",
      detail: `${initialCapacityTarget.users} users with ${initialCapacityTarget.activeWorkspacesPerMinute} active workspaces/minute is the first public target.`,
    },
    {
      label: "Cost-control policy",
      status: "ready",
      detail: `${scaleRateLimitPolicies.length} route classes have explicit request windows and cost weights ready for API enforcement.`,
    },
    {
      label: "Checkout",
      status: "ready",
      detail: "Stripe Checkout is wired for Creator and Growth subscriptions, with Operator kept application-based.",
    },
    {
      label: "Load proof",
      status: "next",
      detail: "Run synthetic login, AI-build, and X-refresh load tests before inviting the full 500-user cohort.",
    },
  ];
}
