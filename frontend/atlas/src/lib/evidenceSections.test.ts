import { splitEvidenceSections } from "./evidenceSections";

describe("splitEvidenceSections", () => {
  it("keeps representatives and bridges out of long tail pagination", () => {
    const sections = splitEvidenceSections({
      representatives: [
        { source_item_id: 1, is_representative: true, is_bridge: false },
      ],
      bridges: [
        { source_item_id: 2, is_representative: false, is_bridge: true },
      ],
      long_tail_page: {
        items: [
          { source_item_id: 3, is_representative: false, is_bridge: false },
        ],
        limit: 1,
        offset: 0,
        total: 1,
      },
      section_totals: {
        representatives: 1,
        bridges: 1,
        long_tail: 1,
      },
    });

    expect(sections.representatives).toHaveLength(1);
    expect(sections.bridges).toHaveLength(1);
    expect(sections.longTail.items).toHaveLength(1);
    expect(sections.longTail.items[0]?.source_item_id).toBe(3);
  });

  it("preserves section totals while keeping the three evidence buckets distinct", () => {
    const sections = splitEvidenceSections({
      representatives: [
        { source_item_id: 11, is_representative: true, is_bridge: false },
      ],
      bridges: [
        { source_item_id: 22, is_representative: false, is_bridge: true },
      ],
      long_tail_page: {
        items: [
          { source_item_id: 33, is_representative: false, is_bridge: false },
          { source_item_id: 44, is_representative: false, is_bridge: false },
        ],
        limit: 2,
        offset: 0,
        total: 7,
      },
      section_totals: {
        representatives: 1,
        bridges: 1,
        long_tail: 7,
      },
    });

    expect(sections.representatives.map((item) => item.source_item_id)).toEqual([11]);
    expect(sections.bridges.map((item) => item.source_item_id)).toEqual([22]);
    expect(sections.longTail.items.map((item) => item.source_item_id)).toEqual([33, 44]);
    expect(sections.totals).toEqual({
      representatives: 1,
      bridges: 1,
      longTail: 7,
    });
  });

  it("filters long-tail entries that also appear in representative or bridge sections", () => {
    const sections = splitEvidenceSections({
      representatives: [
        { source_item_id: 11, is_representative: true, is_bridge: false },
      ],
      bridges: [
        { source_item_id: 22, is_representative: false, is_bridge: true },
      ],
      long_tail_page: {
        items: [
          { source_item_id: 11, is_representative: true, is_bridge: false },
          { source_item_id: 22, is_representative: false, is_bridge: true },
          { source_item_id: 33, is_representative: false, is_bridge: false },
        ],
        limit: 3,
        offset: 0,
        total: 3,
      },
      section_totals: {
        representatives: 1,
        bridges: 1,
        long_tail: 3,
      },
    });

    expect(sections.longTail.items.map((item) => item.source_item_id)).toEqual([33]);
  });
});
