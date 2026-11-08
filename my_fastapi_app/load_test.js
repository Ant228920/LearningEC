import http from 'k6/http';
import { check, sleep } from 'k6';

const MODE = __ENV.MODE || 'normal';

const scenarios = {
  normal: {
    executor: 'ramping-vus',
    startVUs: 1,
    stages: [
      { duration: '10s', target: 10 },
      { duration: '20s', target: 10 },
      { duration: '5s', target: 0 },
    ],
  },
  stress: {
    executor: 'ramping-vus',
    startVUs: 10,
    stages: [
      { duration: '5s', target: 100 },
      { duration: '20s', target: 150 },
      { duration: '5s', target: 0 },
    ],
  },
};

export const options = {
  scenarios: {
    load_test: scenarios[MODE],
  },
  thresholds: {
    http_req_duration: ['p(95)<200'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const url = 'http://localhost:8000/api/v1/tasks/api/convert?amount=100&from_currency=UAH&to_currency=EUR';

  const res = http.get(url);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has converted_amount': (r) => r.json().hasOwnProperty('converted_amount'),
  });

  sleep(0.05);
}