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

export const IconAssistant = (): ReactNode => (
  <Svg>
    <rect x="4" y="8" width="16" height="12" rx="2" />
    <path d="M12 8V4M9 2h6M9 14h.01M15 14h.01M9 20h6" />
  </Svg>
);
export const IconCalendar = (): ReactNode => (
  <Svg>
    <rect x="3" y="4" width="18" height="17" rx="2" />
    <path d="M3 9h18M8 2v4M16 2v4" />
  </Svg>
);
export const IconMap = (): ReactNode => (
  <Svg>
    <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z" />
    <path d="M9 4v14M15 6v14" />
  </Svg>
);
export const IconEnterprises = (): ReactNode => (
  <Svg>
    <rect x="4" y="3" width="16" height="18" rx="1" />
    <path d="M9 21v-6h6v6M9 7h.01M12 7h.01M15 7h.01M9 11h.01M12 11h.01M15 11h.01" />
  </Svg>
);
export const IconPlatforms = (): ReactNode => (
  <Svg>
    <rect x="3" y="4" width="18" height="7" rx="1.5" />
    <rect x="3" y="13" width="18" height="7" rx="1.5" />
    <path d="M7 7.5h.01M7 16.5h.01" />
  </Svg>
);
export const IconEnforcement = (): ReactNode => (
  <Svg>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="M9 12l2 2 4-4" />
  </Svg>
);
export const IconInspection = (): ReactNode => (
  <Svg>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </Svg>
);
export const IconReview = (): ReactNode => (
  <Svg>
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
    <path d="M14 3v6h6M9 15l2 2 4-4" />
  </Svg>
);
export const IconArchive = (): ReactNode => (
  <Svg>
    <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-1L9.6 3.3A2 2 0 0 0 7.9 2H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2z" />
    <path d="M9 13h6" />
  </Svg>
);
export const IconKnowledge = (): ReactNode => (
  <Svg>
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z" />
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 22H20" />
  </Svg>
);
export const IconMcp = (): ReactNode => (
  <Svg>
    <path d="M12 22v-5M9 8V2M15 8V2M18 8v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z" />
  </Svg>
);
export const IconSettings = (): ReactNode => (
  <Svg>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Svg>
);
export const IconChevron = (): ReactNode => (
  <Svg>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);
export const IconShield = (): ReactNode => (
  <Svg>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="M12 8v6M9 11h6" />
  </Svg>
);
export const IconTasks = (): ReactNode => (
  <Svg>
    <path d="M11 17h6M11 13h6M11 9h6" />
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M7 9l.01 0M7 13l.01 0M7 17l.01 0" />
  </Svg>
);
export const IconDashboard = (): ReactNode => (
  <Svg>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </Svg>
);
export const IconAIExpert = (): ReactNode => (
  <Svg>
    <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.38-1 1.72V7h3a2 2 0 0 1 2 2v3h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-1v3a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-3H5a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2h1V9a2 2 0 0 1 2-2h3V5.72A1.99 1.99 0 0 1 10 4a2 2 0 0 1 2-2z" />
    <circle cx="8.5" cy="12.5" r="1.5" /><circle cx="15.5" cy="12.5" r="1.5" />
  </Svg>
);
