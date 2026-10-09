import { redirect } from "next/navigation";

/** 根路径默认落地：告警看板（审核员默认落地待办中心，D14 接角色分流） */
export default function Home() {
  redirect("/alarms");
}
