const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
type I = { size?: number };

export const Logo = ({ size = 22 }: I) => (
  <svg width={size} height={size} viewBox="0 0 26 26" fill="none">
    <circle cx="6" cy="7" r="3.2" fill="#fff" /><circle cx="20" cy="6" r="2.6" fill="#fff" opacity=".85" />
    <circle cx="13" cy="19" r="3.6" fill="#fff" /><circle cx="21.5" cy="18" r="2.2" fill="#fff" opacity=".75" />
    <path d="M6 7L13 19M20 6L13 19M20 6L21.5 18M6 7L20 6" stroke="#fff" strokeWidth="1.4" opacity=".8" />
  </svg>
);
export const Calendar = ({ size = 15 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>);
export const Pin = ({ size = 15 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>);
export const Send = ({ size = 16 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M5 12h13M13 6l6 6-6 6" /></svg>);
export const Stop = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" /></svg>);
export const Plus = ({ size = 15 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M12 5v14M5 12h14" /></svg>);
export const Minus = ({ size = 15 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M5 12h14" /></svg>);
export const Fit = ({ size = 15 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4" /></svg>);
export const Check = ({ size = 12 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P} strokeWidth={3}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>);
export const Cross = ({ size = 12 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P} strokeWidth={3}><path d="M6 6l12 12M18 6L6 18" /></svg>);
export const External = ({ size = 13 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>);
export const Doc = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>);
export const Graph = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="8" r="2.5" /><circle cx="10" cy="18" r="2.5" /><path d="M8 7.5l7.5.8M7 8.3l2.2 7.4M16.3 10l-4.6 6.3" /></svg>);
export const List = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" /></svg>);
export const Sparkle = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9zM19 15l.9 2.6 2.6.9-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z" /></svg>);
export const Globe = ({ size = 14 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.8 3 2.8 15 0 18M12 3c-2.8 3-2.8 15 0 18" /></svg>);
export const Warn = ({ size = 13 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4M12 17.5h.01" /></svg>);
export const Arrow = ({ size = 12 }: I) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P}><path d="M9 6l6 6-6 6" /></svg>);
