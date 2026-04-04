"use client";

import React, { useRef, useEffect } from "react";
import "./magic-bento.css";

interface BentoCardProps {
  color?: string;
  title?: React.ReactNode;
  description?: React.ReactNode;
  label?: React.ReactNode;
}

interface BentoProps {
  data: BentoCardProps[];
}

export default function MagicBento({ data }: BentoProps) {
  return (
    <div className="card-grid">
      {data.map((card, index) => (
        <div
          key={index}
          className="magic-bento-card"
          style={{ backgroundColor: card.color }}
        >
          <div className="magic-bento-card__header">
            <div className="magic-bento-card__label">{card.label}</div>
          </div>
          <div className="magic-bento-card__content">
            <h2 className="magic-bento-card__title">{card.title}</h2>
            <div className="magic-bento-card__description">{card.description}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
