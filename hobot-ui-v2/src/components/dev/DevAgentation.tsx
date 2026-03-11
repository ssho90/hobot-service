import { lazy, Suspense } from 'react';
import type { AgentationProps } from 'agentation';

const Agentation = import.meta.env.DEV
  ? lazy(async () => {
      const module = await import('agentation');
      return { default: module.Agentation };
    })
  : null;

const env = import.meta.env as ImportMetaEnv & {
  readonly VITE_AGENTATION_ENDPOINT?: string;
};

const defaultEndpoint = 'http://localhost:4747';

export function DevAgentation() {
  if (!import.meta.env.DEV || Agentation === null) {
    return null;
  }

  const props: AgentationProps = {
    endpoint: env.VITE_AGENTATION_ENDPOINT?.trim() || defaultEndpoint,
    onSessionCreated: (sessionId) => {
      console.info(`[agentation] session created: ${sessionId}`);
    },
  };

  return (
    <Suspense fallback={null}>
      <Agentation {...props} />
    </Suspense>
  );
}
