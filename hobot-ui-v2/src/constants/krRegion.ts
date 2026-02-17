const SIDO_NAME_BY_PREFIX: Record<string, string> = {
  '11': '서울',
  '26': '부산',
  '27': '대구',
  '28': '인천',
  '29': '광주',
  '30': '대전',
  '31': '울산',
  '36': '세종',
  '41': '경기',
  '42': '강원',
  '43': '충북',
  '44': '충남',
  '45': '전북',
  '46': '전남',
  '47': '경북',
  '48': '경남',
  '50': '제주',
};

const normalizeSearchToken = (value: string): string => value.replace(/\s+/g, '').toLowerCase();

// Phase2 적재 범위 기준 LAWD_CD -> 한글 지역명
export const LAWd_NAME_BY_CODE: Record<string, string> = {
  // 서울
  '11110': '서울 종로구',
  '11140': '서울 중구',
  '11170': '서울 용산구',
  '11200': '서울 성동구',
  '11215': '서울 광진구',
  '11230': '서울 동대문구',
  '11260': '서울 중랑구',
  '11290': '서울 성북구',
  '11305': '서울 강북구',
  '11320': '서울 도봉구',
  '11350': '서울 노원구',
  '11380': '서울 은평구',
  '11410': '서울 서대문구',
  '11440': '서울 마포구',
  '11470': '서울 양천구',
  '11500': '서울 강서구',
  '11530': '서울 구로구',
  '11545': '서울 금천구',
  '11560': '서울 영등포구',
  '11590': '서울 동작구',
  '11620': '서울 관악구',
  '11650': '서울 서초구',
  '11680': '서울 강남구',
  '11710': '서울 송파구',
  '11740': '서울 강동구',

  // 경기
  '41111': '경기 수원시 장안구',
  '41113': '경기 수원시 권선구',
  '41115': '경기 수원시 팔달구',
  '41117': '경기 수원시 영통구',
  '41131': '경기 성남시 수정구',
  '41133': '경기 성남시 중원구',
  '41135': '경기 성남시 분당구',
  '41150': '경기 의정부시',
  '41171': '경기 안양시 만안구',
  '41173': '경기 안양시 동안구',
  '41190': '경기 부천시',
  '41210': '경기 광명시',
  '41220': '경기 평택시',
  '41250': '경기 동두천시',
  '41271': '경기 안산시 상록구',
  '41273': '경기 안산시 단원구',
  '41281': '경기 고양시 덕양구',
  '41285': '경기 고양시 일산동구',
  '41287': '경기 고양시 일산서구',
  '41290': '경기 과천시',
  '41310': '경기 구리시',
  '41360': '경기 남양주시',
  '41370': '경기 오산시',
  '41390': '경기 시흥시',
  '41410': '경기 군포시',
  '41430': '경기 의왕시',
  '41450': '경기 하남시',
  '41460': '경기 용인시 처인구',
  '41463': '경기 용인시 기흥구',
  '41465': '경기 용인시 수지구',
  '41480': '경기 파주시',
  '41500': '경기 이천시',
  '41550': '경기 안성시',
  '41570': '경기 김포시',
  '41590': '경기 화성시',
  '41610': '경기 광주시',
  '41630': '경기 양주시',
  '41650': '경기 포천시',
  '41670': '경기 여주시',
  '41800': '경기 연천군',
  '41820': '경기 가평군',
  '41830': '경기 양평군',

  // 부산
  '26110': '부산 중구',
  '26140': '부산 서구',
  '26170': '부산 동구',
  '26200': '부산 영도구',
  '26230': '부산 부산진구',
  '26260': '부산 동래구',
  '26290': '부산 남구',
  '26320': '부산 북구',
  '26350': '부산 해운대구',
  '26380': '부산 사하구',
  '26410': '부산 금정구',
  '26440': '부산 강서구',
  '26470': '부산 연제구',
  '26500': '부산 수영구',
  '26530': '부산 사상구',
  '26710': '부산 기장군',

  // 대구
  '27110': '대구 중구',
  '27140': '대구 동구',
  '27170': '대구 서구',
  '27200': '대구 남구',
  '27230': '대구 북구',
  '27260': '대구 수성구',
  '27290': '대구 달서구',
  '27710': '대구 달성군',
  '27720': '대구 군위군',

  // 인천
  '28110': '인천 중구',
  '28140': '인천 동구',
  '28177': '인천 미추홀구',
  '28185': '인천 연수구',
  '28200': '인천 남동구',
  '28237': '인천 부평구',
  '28245': '인천 계양구',
  '28260': '인천 서구',
  '28710': '인천 강화군',
  '28720': '인천 옹진군',

  // 광주
  '29110': '광주 동구',
  '29140': '광주 서구',
  '29155': '광주 남구',
  '29170': '광주 북구',
  '29200': '광주 광산구',

  // 대전
  '30110': '대전 동구',
  '30140': '대전 중구',
  '30170': '대전 서구',
  '30200': '대전 유성구',
  '30230': '대전 대덕구',

  // 울산
  '31110': '울산 중구',
  '31140': '울산 남구',
  '31170': '울산 동구',
  '31200': '울산 북구',
  '31710': '울산 울주군',

  // 세종
  '36110': '세종',

  // 강원
  '42110': '강원 춘천시',
  '42130': '강원 원주시',
  '42150': '강원 강릉시',

  // 충북
  '43111': '충북 청주시 상당구',
  '43112': '충북 청주시 서원구',
  '43113': '충북 청주시 흥덕구',
  '43114': '충북 청주시 청원구',

  // 충남
  '44131': '충남 천안시 동남구',
  '44133': '충남 천안시 서북구',
  '44200': '충남 아산시',

  // 전북
  '45111': '전북 전주시 완산구',
  '45113': '전북 전주시 덕진구',
  '45140': '전북 익산시',

  // 전남
  '46110': '전남 목포시',
  '46130': '전남 여수시',
  '46150': '전남 순천시',

  // 경북
  '47111': '경북 포항시 남구',
  '47113': '경북 포항시 북구',
  '47130': '경북 경주시',
  '47190': '경북 구미시',
  '47210': '경북 영주시',
  '47290': '경북 김천시',

  // 경남
  '48121': '경남 창원시 의창구',
  '48123': '경남 창원시 성산구',
  '48125': '경남 창원시 마산합포구',
  '48127': '경남 창원시 마산회원구',
  '48129': '경남 창원시 진해구',
  '48170': '경남 진주시',
  '48250': '경남 김해시',

  // 제주
  '50110': '제주 제주시',
  '50130': '제주 서귀포시',
};

const NAME_TO_CODE: Record<string, string> = Object.entries(LAWd_NAME_BY_CODE).reduce(
  (acc, [code, name]) => {
    const normalized = normalizeSearchToken(name);
    acc[normalized] = code;
    return acc;
  },
  {} as Record<string, string>
);

export type LawdRegionItem = {
  code: string;
  name: string;
  sidoName: string;
  districtName: string;
};

export const getSidoName = (lawdCd: unknown): string => {
  const code = String(lawdCd ?? '').trim();
  if (code.length < 2) return '';
  return SIDO_NAME_BY_PREFIX[code.slice(0, 2)] ?? '';
};

const SIDO_PREFIX_BY_NAME: Record<string, string> = {
  서울: '11',
  서울시: '11',
  부산: '26',
  부산시: '26',
  대구: '27',
  대구시: '27',
  인천: '28',
  인천시: '28',
  광주: '29',
  광주시: '29',
  대전: '30',
  대전시: '30',
  울산: '31',
  울산시: '31',
  세종: '36',
  세종시: '36',
  경기: '41',
  경기도: '41',
  강원: '42',
  강원도: '42',
  충북: '43',
  충청북도: '43',
  충남: '44',
  충청남도: '44',
  전북: '45',
  전라북도: '45',
  전남: '46',
  전라남도: '46',
  경북: '47',
  경상북도: '47',
  경남: '48',
  경상남도: '48',
  제주: '50',
  제주도: '50',
  seoul: '11',
  busan: '26',
  daegu: '27',
  incheon: '28',
  gwangju: '29',
  daejeon: '30',
  ulsan: '31',
  sejong: '36',
  gyeonggi: '41',
  gangwon: '42',
  chungbuk: '43',
  chungnam: '44',
  jeonbuk: '45',
  jeonnam: '46',
  gyeongbuk: '47',
  gyeongnam: '48',
  jeju: '50',
};

const LAWD_REGION_ITEMS: LawdRegionItem[] = Object.entries(LAWd_NAME_BY_CODE)
  .map(([code, name]) => {
    const sidoName = getSidoName(code);
    const districtName = name.startsWith(`${sidoName} `) ? name.slice(sidoName.length + 1) : name;
    return {
      code,
      name,
      sidoName,
      districtName,
    };
  })
  .sort((left, right) => left.code.localeCompare(right.code));

const ALL_LAWD_CODES = Object.keys(LAWd_NAME_BY_CODE).sort();

const SIDO_PREFIX_BY_TOKEN: Record<string, string> = Object.entries(SIDO_PREFIX_BY_NAME).reduce(
  (acc, [name, prefix]) => {
    acc[normalizeSearchToken(name)] = prefix;
    return acc;
  },
  {} as Record<string, string>
);

const SPECIAL_REGION_ITEMS: LawdRegionItem[] = [
  {
    code: 'ALL',
    name: '전국 전체',
    sidoName: '전국',
    districtName: '전체',
  },
  ...Object.entries(SIDO_NAME_BY_PREFIX).map(([prefix, sidoName]) => ({
    code: `${prefix}000`,
    name: `${sidoName} 전체`,
    sidoName,
    districtName: '전체',
  })),
];

export const getLawdRegionName = (lawdCd: unknown): string => {
  const code = String(lawdCd ?? '').trim();
  if (!code) return '-';
  const detailName = LAWd_NAME_BY_CODE[code];
  if (detailName) return detailName;
  const sidoName = getSidoName(code);
  return sidoName || code;
};

export const parseLawdInputToCodes = (
  input: string
): { codes: string[]; unknownTokens: string[] } => {
  const trimmed = input.trim();
  if (!trimmed) {
    return { codes: [], unknownTokens: [] };
  }

  const codes = new Set<string>();
  const unknownTokens: string[] = [];

  trimmed
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean)
    .forEach((token) => {
      const normalized = normalizeSearchToken(token);

      if (/^\d{5}$/.test(token)) {
        codes.add(token);
        return;
      }

      const exactCode = NAME_TO_CODE[normalized];
      if (exactCode) {
        codes.add(exactCode);
        return;
      }

      if (
        normalized === '전국' ||
        normalized === '전체' ||
        normalized === '전국전체' ||
        normalized === '전체지역' ||
        normalized === 'all'
      ) {
        ALL_LAWD_CODES.forEach((code) => codes.add(code));
        return;
      }

      const noAllSuffix = normalized.endsWith('전체')
        ? normalized.slice(0, normalized.length - 2)
        : normalized;
      const noEnglishAllSuffix = normalized.endsWith('all')
        ? normalized.slice(0, normalized.length - 3)
        : normalized;

      const prefix =
        SIDO_PREFIX_BY_TOKEN[normalized] ||
        SIDO_PREFIX_BY_TOKEN[noAllSuffix] ||
        SIDO_PREFIX_BY_TOKEN[noEnglishAllSuffix];
      if (prefix) {
        Object.keys(LAWd_NAME_BY_CODE)
          .filter((code) => code.startsWith(prefix))
          .forEach((code) => codes.add(code));
        return;
      }

      unknownTokens.push(token);
    });

  return {
    codes: Array.from(codes).sort(),
    unknownTokens,
  };
};

export const getLawdRegionItems = (): LawdRegionItem[] => LAWD_REGION_ITEMS;

export const searchLawdRegions = (query: string, limit = 12): LawdRegionItem[] => {
  const normalizedQuery = normalizeSearchToken(query.trim());
  if (!normalizedQuery) return [];

  return [...SPECIAL_REGION_ITEMS, ...LAWD_REGION_ITEMS]
    .filter((item) => {
      const normalizedName = normalizeSearchToken(item.name);
      return (
        item.code.includes(normalizedQuery) ||
        normalizedName.includes(normalizedQuery) ||
        normalizeSearchToken(item.sidoName).includes(normalizedQuery) ||
        normalizeSearchToken(item.districtName).includes(normalizedQuery)
      );
    })
    .slice(0, Math.max(1, limit));
};

export type LawdRegionGroup = {
  sidoName: string;
  items: LawdRegionItem[];
};

export const getLawdRegionTree = (): LawdRegionGroup[] => {
  const groupPriority: Record<string, number> = {
    서울: 0,
    경기: 1,
  };

  const groupMap = new Map<string, LawdRegionItem[]>();
  LAWD_REGION_ITEMS.forEach((item) => {
    const key = item.sidoName || '기타';
    const bucket = groupMap.get(key) ?? [];
    bucket.push(item);
    groupMap.set(key, bucket);
  });

  return Array.from(groupMap.entries())
    .map(([sidoName, items]) => ({
      sidoName,
      items: [...items].sort((left, right) => {
        const byDistrict = left.districtName.localeCompare(right.districtName, 'ko');
        if (byDistrict !== 0) return byDistrict;
        const byName = left.name.localeCompare(right.name, 'ko');
        if (byName !== 0) return byName;
        return left.code.localeCompare(right.code);
      }),
    }))
    .sort((left, right) => {
      const leftPriority = groupPriority[left.sidoName] ?? 999;
      const rightPriority = groupPriority[right.sidoName] ?? 999;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;
      return left.sidoName.localeCompare(right.sidoName, 'ko');
    });
};
