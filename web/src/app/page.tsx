import { Suspense } from "react";
import { cookies } from "next/headers";

import { PublicLanding } from "@/components/public-landing";
import { StreamlitWebsitePreview } from "@/components/streamlit-website-preview";
import { extensionSessionCookieName } from "@/lib/extension-session";
import { buildRuntimeReadinessFromCookieValue } from "@/lib/runtime-readiness";

type HomeSearchParams = {
  page?: string | string[];
  preview?: string | string[];
  tool?: string | string[];
};

function getFirstSearchValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function shouldShowWorkspacePreview(searchParams: HomeSearchParams) {
  const previewMode = getFirstSearchValue(searchParams.preview);

  return Boolean(
    searchParams.page ||
      searchParams.tool ||
      previewMode === "workspace" ||
      previewMode === "app" ||
      previewMode === "streamlit",
  );
}

export default async function HomePage({
  searchParams,
}: {
  searchParams?: Promise<HomeSearchParams>;
}) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const cookieStore = await cookies();
  const readiness = buildRuntimeReadinessFromCookieValue(
    cookieStore.get(extensionSessionCookieName)?.value,
  );
  const debugChecklist = readiness.operatorChecklist.map((item) => ({
    label: item.label,
    ready: item.status === "ready",
  }));

  if (!shouldShowWorkspacePreview(resolvedSearchParams)) {
    return <PublicLanding />;
  }

  return (
    <Suspense fallback={null}>
      <StreamlitWebsitePreview debugChecklist={debugChecklist} />
    </Suspense>
  );
}
