import type { ReactNode } from 'react';

function Svg({ children }: { children: ReactNode }): ReactNode {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      width="100%"
      height="100%"
    >
      {children}
    </svg>
  );
}

/* ---- Section ① Office ---- */
export const IconFileText = (): ReactNode => (
  <Svg><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8M8 17h8M8 9h2" /></Svg>
);
export const IconFileSpreadsheet = (): ReactNode => (
  <Svg><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M4 9h16M4 15h16M8 3v18M16 3v18" /></Svg>
);
export const IconFilePdf = (): ReactNode => (
  <Svg><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M8 12h.01M11 12h.01M14 12h.01" /></Svg>
);
export const IconPenTool = (): ReactNode => (
  <Svg><path d="M12 20h9" /><path d="m16.5 3.5 4 4L7 21H3v-4L16.5 3.5z" /></Svg>
);
export const IconMessageSquare = (): ReactNode => (
  <Svg><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /><path d="M8 9h8M8 13h6" /></Svg>
);

/* ---- Section ② GIS ---- */
export const IconMapPin = (): ReactNode => (
  <Svg><circle cx="12" cy="10" r="3" /><path d="M12 2a8 8 0 0 0-8 8c0 6 8 14 8 14s8-8 8-14a8 8 0 0 0-8-8z" /></Svg>
);
export const IconCompass = (): ReactNode => (
  <Svg><circle cx="12" cy="12" r="9" /><path d="m16.2 7.8-4.2 4.2-4.2-4.2M7.8 16.2l4.2-4.2 4.2 4.2" /></Svg>
);

/* ---- Section ③ Hermes ---- */
export const IconRefreshCw = (): ReactNode => (
  <Svg><path d="M23 4v6h-6" /><path d="M1 20v-6h6" /><path d="M3.5 9a9 9 0 0 1 14.8-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15" /></Svg>
);
export const IconZap = (): ReactNode => (
  <Svg><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></Svg>
);

/* ---- Section ④ Review ---- */
export const IconTrendingUp = (): ReactNode => (
  <Svg><path d="m23 6-9.5 9.5-5-5L1 18" /><path d="M17 6h6v6" /></Svg>
);
export const IconBarChart3 = (): ReactNode => (
  <Svg><rect x="3" y="13" width="4" height="8" rx="1" /><rect x="10" y="9" width="4" height="12" rx="1" /><rect x="17" y="4" width="4" height="17" rx="1" /></Svg>
);

/* ---- Pin / Plus / More ---- */
export const IconPin = (): ReactNode => (
  <Svg><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" /><circle cx="12" cy="12" r="2" /></Svg>
);
export const IconPlus = (): ReactNode => (
  <Svg><path d="M12 5v14M5 12h14" /></Svg>
);

/* ---- Chat Input Tools ---- */
export const IconPaperclip = (): ReactNode => (
  <Svg><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></Svg>
);
export const IconMic = (): ReactNode => (
  <Svg><rect x="9" y="1" width="6" height="11" rx="3" /><path d="M5 10a7 7 0 0 0 14 0" /><path d="M12 18v4M8 22h8" /></Svg>
);
export const IconSend = (): ReactNode => (
  <Svg><path d="M22 2 11 13" /><path d="m22 2-7 20-4-9-9-4z" /></Svg>
);
