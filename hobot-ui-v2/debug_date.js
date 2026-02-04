
const parseCycleDate = (value) => {
    if (typeof value !== 'string') {
        console.log(`Invalid value type: ${typeof value}, val: ${value}`);
        return null;
    }
    const parts = value.split('-');
    console.log(`Split '${value}':`, parts);
    const [year, month] = parts.map((part) => Number(part));
    console.log(`Parsed year: ${year}, month: ${month}`);
    if (!year || !month) return null;
    const utc = Date.UTC(year, month - 1, 1);
    console.log(`UTC: ${utc} (${new Date(utc).toISOString()})`);
    return utc;
};

const items = [
    { "date": "2012-11" },
    { "date": "2026-10" },
];

items.forEach(item => parseCycleDate(item.date));
