import React from 'react';
import { useTheme } from '../context/ThemeContext.jsx';

export default function SpuLogo({ collapsed = false }) {
  const { isDark } = useTheme();

  if (collapsed) {
    return (
      <div className="flex items-center justify-center select-none">
        <img
          src="/spu-crest.png"
          alt="Sol Plaatje University Crest"
          draggable={false}
          style={{
            filter: isDark
              ? 'none'
              : 'drop-shadow(0 1px 2px rgba(15, 23, 42, 0.12))',
          }}
          className="h-10 w-auto object-contain transition-all duration-200"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center select-none">
      <img
        src={isDark ? '/spu-logo-dark.png' : '/spu-logo-light.png'}
        alt="Sol Plaatje University"
        draggable={false}
        style={{
          filter: isDark
            ? 'none'
            : 'drop-shadow(0 1px 2px rgba(15, 23, 42, 0.10))',
        }}
        className="h-[92px] w-auto object-contain transition-all duration-200"
      />
    </div>
  );
}
