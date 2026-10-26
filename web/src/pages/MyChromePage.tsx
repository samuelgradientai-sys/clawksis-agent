import { useEffect } from "react";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useProfileScope } from "@/contexts/useProfileScope";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { myChromeCopy as copy } from "@/components/my-chrome/copy";
import {
  PaymentsPanel,
  SafetyPanel,
  SetupSteps,
  SharedTabs,
  StatusHero,
} from "@/components/my-chrome/MyChromePanels";
import { useMyChrome } from "@/components/my-chrome/useMyChrome";

/** "Mi Chrome": let the agent drive the user's own Chrome through a paired extension. */
export default function MyChromePage() {
  const { locale } = useI18n();
  const { setTitle } = usePageHeader();
  const { profile } = useProfileScope();
  const { toast, showToast } = useToast();
  const data = useMyChrome(profile, showToast);

  useEffect(() => setTitle(copy.pageTitle), [setTitle]);

  const status = data.status;
  return (
    <div className="mx-auto flex w-full min-w-0 max-w-4xl flex-col gap-4 pb-8 sm:gap-5">
      <Toast toast={toast} />
      {data.loadError && !status && <LoadErrorNotice what={copy.loadWhat} detail={data.loadError} onRetry={data.reload} />}
      {!status && !data.loadError && (
        <div className="flex justify-center py-24">
          <Spinner className="text-2xl text-primary" />
        </div>
      )}
      {status && (
        <>
          <StatusHero data={data} locale={locale} status={status} />
          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 lg:gap-5">
            <SetupSteps data={data} locale={locale} status={status} />
            <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
              <PaymentsPanel data={data} status={status} />
              <SharedTabs status={status} />
              <SafetyPanel data={data} status={status} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
