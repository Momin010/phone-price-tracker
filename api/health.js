export default function handler(req, res) {
  res.status(200).json({ ok: true, service: 'phone-price-tracker', time: new Date().toISOString() });
}
