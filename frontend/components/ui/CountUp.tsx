"use client";
import { useEffect } from "react";
import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useMotionSafe } from ".";
export default function CountUp({value}:{value:number}) {const number=useMotionValue(value);const formatted=useTransform(number,v=>v.toFixed(1));const safe=useMotionSafe();useEffect(()=>{const control=animate(number,value,{duration:safe ? .7 : 0});return()=>control.stop();},[value,number,safe]);return <motion.span aria-label={`Calculated score ${value.toFixed(1)}`}>{formatted}</motion.span>;}
