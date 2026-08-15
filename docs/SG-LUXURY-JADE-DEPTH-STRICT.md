# SG Luxury Jade Depth — SG-Gateway strict transfer

This build uses the approved standard exactly for the light theme:

- radial background: `#FBF4E8 → #F1EEE6 → #E5ECE7`, centre `78% -8%`, radius `68%`;
- header: `#F1F3EF → #DCE4DD`;
- sidebar: `#E8EFF2 → #D8E1E4`;
- card: `#FEFCF7 → #F2ECE1`;
- nested surface: `#F1EADE → #E1D8CA`;
- raised surface: `#F8F0E4 → #E8D9C3`;
- input: `#FFFDFC → #F6F1E7`;
- disabled: `#F6F0E6 → #E7DCCB`;
- active tile: `#739E88 → #4E7965`;
- action/hover/pressed: exact approved jade gradients;
- button shadow: `0 2px 12px rgba(43,52,46,.20)`;
- card shadow: `0 4px 18px rgba(43,52,46,.17)`;
- light rim: WPF `#55FFFFFF`; in CSS use the exact alpha-white equivalent `rgba(255, 255, 255, .333)`, top and sides only;
- radii: buttons 10px, tiles 12px, cards 14/18px;
- champagne `#B88A45` is decoration, warning and key-action border only;
- dark theme is untouched.

Every page component is assigned an explicit material role in its Jinja template.
