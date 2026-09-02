import { useRoute } from './router';
import { Landing } from './screens/Landing';
import { CallScreen } from './screens/CallScreen';
import { Account } from './screens/Account';

export function App() {
  const { path, navigate } = useRoute();

  if (path === '/call') return <CallScreen navigate={navigate} />;
  if (path === '/account') return <Account navigate={navigate} />;
  return <Landing navigate={navigate} />;
}

export default App;
