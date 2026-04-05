import { CustomerPage } from "../../../components/customer-page";

export default async function Page({ params }) {
  const resolvedParams = await params;
  return <CustomerPage userId={resolvedParams.userId} />;
}
