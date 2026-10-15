"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

export default function Card({ children, className = "", hover, onClick }: CardProps) {
  return (
    <motion.div
      whileHover={hover ? { y: -3 } : undefined}
      onClick={onClick}
      className={`card p-5 ${hover ? "transition-shadow hover:shadow-card cursor-pointer" : ""} ${className}`}
    >
      {children}
    </motion.div>
  );
}
