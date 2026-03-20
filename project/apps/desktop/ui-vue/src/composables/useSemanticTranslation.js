/**
 * 语义标签翻译 + 去重映射 (v3.0 — 400+ entries for 25-category taxonomy)
 */

const translationMap = {
  // ── 场景 / 地点 ──
  'landscape': '风景', 'scenery': '风景', 'nature': '自然',
  'urban': '城市', 'city': '城市', 'cityscape': '城市', 'skyline': '天际线',
  'indoor': '室内', 'outdoor': '户外', 'interior': '室内', 'exterior': '户外',
  'beach': '海滩', 'ocean': '海洋', 'sea': '大海', 'seaside': '海边',
  'mountain': '山', 'mountains': '山脉', 'hill': '山丘', 'summit': '山顶',
  'forest': '森林', 'tree': '树', 'trees': '树木', 'woods': '树林',
  'river': '河流', 'lake': '湖泊', 'water': '水面', 'waterfall': '瀑布',
  'garden': '花园', 'park': '公园', 'field': '田野',
  'sunset': '日落', 'sunrise': '日出', 'dawn': '黎明', 'dusk': '黄昏',
  'night': '夜景', 'sky': '天空', 'cloud': '云', 'clouds': '云',
  'snow': '雪', 'rain': '雨', 'fog': '雾',
  'street': '街道', 'road': '公路', 'highway': '高速公路', 'path': '小路',
  'building': '建筑', 'architecture': '建筑', 'bridge': '桥',
  'temple': '寺庙', 'church': '教堂', 'castle': '城堡',
  'cafe': '咖啡馆', 'library': '图书馆', 'station': '车站', 'airport': '机场',
  'market': '市集', 'classroom': '教室', 'office': '办公室',
  'kitchen': '厨房', 'bedroom': '卧室', 'balcony': '阳台', 'rooftop': '屋顶',
  'plaza': '广场', 'alley': '小巷', 'downtown': '市中心', 'old town': '老城区',

  // ── 人物 / 动作 ──
  'person': '人物', 'people': '人群', 'crowd': '人群',
  'man': '男性', 'woman': '女性', 'child': '儿童', 'children': '儿童',
  'face': '人脸', 'portrait': '肖像', 'selfie': '自拍',
  'walking': '行走', 'running': '跑步', 'sitting': '坐', 'jumping': '跳跃',
  'dancing': '跳舞', 'singing': '唱歌', 'cooking': '烹饪',
  'eating': '用餐', 'drinking': '饮', 'shopping': '购物',
  'travel': '旅行', 'traveling': '旅行', 'traveler': '旅行者',
  'swimming': '游泳', 'driving': '驾驶', 'cycling': '骑行',
  'reading': '阅读', 'writing': '写作', 'photographing': '拍照',
  'chatting': '交谈', 'hugging': '拥抱', 'meditating': '冥想',
  'climbing': '攀登', 'hiking': '徒步', 'skiing': '滑雪', 'surfing': '冲浪',

  // ── 美食 ──
  'food': '美食', 'cuisine': '美食', 'meal': '餐食', 'dish': '菜品',
  'restaurant': '餐厅', 'coffee': '咖啡', 'tea': '茶',
  'fruit': '水果', 'vegetable': '蔬菜', 'meat': '肉',
  'dessert': '甜点', 'cake': '蛋糕', 'bread': '面包',
  'chinese food': '中餐', 'japanese food': '日料', 'western food': '西餐',
  'cocktail': '鸡尾酒', 'barbecue': '烧烤', 'salad': '沙拉',
  'hotpot': '火锅', 'sushi': '寿司', 'pizza': '披萨', 'ice cream': '冰淇淋',

  // ── 动物 ──
  'animal': '动物', 'dog': '狗', 'cat': '猫', 'bird': '鸟',
  'fish': '鱼', 'horse': '马', 'pet': '宠物',
  'butterfly': '蝴蝶', 'dolphin': '海豚', 'deer': '鹿',
  'rabbit': '兔子', 'squirrel': '松鼠', 'seagull': '海鸥', 'bee': '蜜蜂',

  // ── 交通 ──
  'car': '汽车', 'vehicle': '车辆', 'boat': '船', 'airplane': '飞机',
  'bicycle': '自行车', 'motorcycle': '摩托车', 'train': '火车',
  'tram': '电车', 'cable car': '缆车', 'sailboat': '帆船', 'skateboard': '滑板',

  // ── 物品 ──
  'phone': '手机', 'computer': '电脑', 'camera': '相机',
  'book': '书', 'flower': '花', 'flowers': '花',
  'furniture': '家具', 'table': '桌子', 'chair': '椅子',
  'light': '灯光', 'window': '窗户', 'door': '门', 'mirror': '镜子',
  'cup': '杯子', 'instrument': '乐器', 'painting': '画作',

  // ── 服饰 ──
  'clothing': '服装', 'fashion': '时尚',
  'suit': '西装', 'dress': '连衣裙', 'sportswear': '运动装',
  'hanfu': '汉服', 'kimono': '和服', 'denim': '牛仔',
  'accessories': '配饰', 'hat': '帽子', 'scarf': '围巾', 'sneakers': '运动鞋',

  // ── 材质 ──
  'wood': '木质', 'metal': '金属', 'glass': '玻璃', 'stone': '石材',
  'concrete': '混凝土', 'leather': '皮革', 'silk': '丝绸', 'linen': '棉麻',
  'ceramic': '陶瓷', 'bamboo': '竹子', 'paper': '纸张', 'brick': '砖块',
  'marble': '大理石', 'rust': '铁锈', 'plush': '毛绒',

  // ── 建筑风格 ──
  'gothic': '哥特式', 'baroque': '巴洛克', 'modernist': '现代主义',
  'chinese traditional': '中式传统', 'japanese style': '日式和风',
  'mediterranean': '地中海', 'industrial': '工业风',
  'bauhaus': '包豪斯', 'neoclassical': '新古典',
  'postmodern': '后现代', 'art deco': '装饰艺术',
  'minimalist architecture': '极简建筑',

  // ── 身体语言 ──
  'smiling': '微笑', 'thinking': '思考', 'pointing': '指向',
  'clapping': '鼓掌', 'waving': '挥手', 'hands on hips': '叉腰',
  'leaning': '俯身', 'looking up': '仰望', 'head down': '低头',
  'arms crossed': '双臂交叉',

  // ── 色彩 ──
  'warm tones': '暖色调', 'cool tones': '冷色调',
  'morandi': '莫兰迪', 'color blocking': '撞色',
  'monochrome': '黑白', 'gradient': '渐变',
  'high contrast': '高对比', 'soft palette': '柔和',
  'golden': '金色', 'blue tones': '蓝调',

  // ── 构图 ──
  'rule of thirds': '三分法', 'centered': '居中',
  'diagonal': '对角线', 'frame within frame': '框中框',
  'negative space': '留白', 'golden spiral': '黄金螺旋',
  'overhead': '俯拍', 'low angle': '仰拍',
  'foreground': '前景', 'background': '背景',
  'symmetry': '对称', 'leading line': '引导线',

  // ── 自然景观 ──
  'glacier': '冰川', 'canyon': '峡谷', 'desert': '沙漠',
  'grassland': '草原', 'coral reef': '珊瑚礁',
  'volcano': '火山', 'wetland': '湿地', 'cave': '洞穴',

  // ── 天气 ──
  'sunny': '晴天', 'cloudy': '多云', 'rainy': '雨天', 'snowy': '雪天',
  'foggy': '雾', 'rainbow': '彩虹', 'storm': '暴风雨',
  'starry': '星空', 'aurora': '极光',

  // ── 风格 / 属性 ──
  'beautiful': '美丽', 'colorful': '色彩丰富', 'vibrant': '鲜艳',
  'dark': '暗', 'bright': '明亮', 'warm': '温暖', 'cool': '清凉',
  'vintage': '复古', 'modern': '现代', 'traditional': '传统',
  'luxury': '奢华', 'simple': '简约', 'elegant': '优雅',
  'aesthetic': '美学', 'artistic': '艺术',
  'romantic': '浪漫', 'dramatic': '戏剧性', 'peaceful': '宁静',
  'happy': '快乐', 'sad': '忧伤', 'funny': '有趣',
  'cinematic': '电影感', 'documentary': '纪实', 'aerial': '航拍',
  'retro': '复古', 'cyberpunk': '赛博朋克', 'film grain': '胶片感',
  'timelapse': '延时', 'high saturation': '高饱和', 'desaturated': '低饱和',
  'ink wash': '水墨风', 'minimal': '极简',

  // ── 氛围 ──
  'healing': '治愈', 'calm': '宁静', 'energetic': '活力',
  'atmospheric': '氛围感', 'ambient': '环境氛围', 'tranquil': '恬静', 'serene': '宁谧',
  'epic': '史诗感', 'lonely': '孤独', 'tense': '紧张', 'relaxed': '轻松',
  'melancholic': '忧郁', 'joyful': '欢快', 'mysterious': '神秘',
  'solemn': '庄严', 'passionate': '激昂', 'lazy': '慵懒',
  'relaxed vibe': '松弛感',

  // ── 音频 ──
  'light music': '轻音乐', 'electronic': '电子乐',
  'classical': '古典', 'jazz': '爵士', 'ambient': '环境音',
  'rhythmic': '节奏感', 'nature sounds': '自然声', 'white noise': '白噪音',
  'a cappella': '人声清唱',

  // ── 文化 ──
  'festival': '节日', 'tradition': '传统', 'religion': '宗教',
  'folklore': '民俗', 'calligraphy': '书法', 'craft': '手工艺',
  'temple fair': '庙会', 'tea ceremony': '茶道', 'ikebana': '花道',
  'dragon dance': '舞龙', 'lantern': '灯笼',

  // ── 品牌/产品 ──
  'tech product': '科技产品', 'beauty/cosmetics': '美妆',
  'fashion brand': '时装', 'sports brand': '运动品牌',
  'home brand': '家居', 'auto brand': '汽车品牌',
  'FMCG': '快消品', 'baby/maternity': '母婴', 'pet products': '宠物用品',

  // ── 社交 ──
  'solitude': '独处', 'date': '约会', 'family': '家庭',
  'friends gathering': '朋友聚会', 'team': '团队',
  'party': '派对', 'meeting': '会议', 'community': '社区',
  'ceremony': '仪式', 'parade': '游行',

  // ── 行业 ──
  'technology': '科技', 'healthcare': '医疗', 'education': '教育',
  'finance': '金融', 'retail': '零售', 'food service': '餐饮',
  'real estate': '房地产', 'tourism': '旅游',
  'manufacturing': '制造业', 'creative industry': '创意产业',
  'sports': '体育', 'entertainment': '娱乐',

  // ── 叙事 ──
  'montage': '蒙太奇', 'parallel narrative': '平行叙事',
  'flashback': '倒叙', 'suspense': '悬念',
  'symbolism': '象征', 'metaphor': '隐喻',
  'contrast': '对比', 'repetition': '重复',

  // ── 概念 ──
  'lifestyle': '生活方式', 'freedom': '自由', 'achievement': '成就',
  'discipline': '自律', 'loneliness': '孤独', 'connection': '连接',
  'growth': '成长', 'anxiety': '焦虑', 'escape': '逃离',
  'ritual': '仪式感', 'productivity': '高效', 'minimalism': '极简',
  'exploration': '探索', 'belonging': '归属感', 'intimacy': '亲密',
  'wellness': '健康', 'nostalgia': '怀旧', 'creativity': '创造力',
  'sustainability': '可持续', 'balance': '平衡',
  'digital nomad': '数字游民', 'remote work': '远程工作',
  'nature therapy': '自然疗愈',

  // ── 用途 ──
  'travel vlog': '旅行vlog', 'city promo': '城市宣传',
  'hotel/airbnb': '酒店民宿', 'coffee brand': '咖啡品牌',
  'fitness/yoga': '健身瑜伽', 'mental health': '心理疗愈',
  'startup/career': '创业职场', 'doc style': '纪录片',
  'commercial': '广告片', 'social short': '社媒短视频',
  'product review': '产品评测', 'wedding': '婚礼活动',
  'music video': '音乐MV', 'corporate': '企业宣传',

  // ── 影视剪辑 / 摄影术语 ──
  'slow motion': '慢动作', 'fast motion': '快动作', 'fast forward': '快进',
  'jump cut': '跳剪', 'match cut': '匹配剪辑', 'cross cut': '交叉剪辑',
  'close-up': '特写', 'closeup': '特写', 'extreme close-up': '极端特写',
  'wide shot': '远景', 'wide angle': '广角',
  'medium shot': '中景', 'medium close-up': '中近景',
  'establishing shot': '建立镜头', 'tracking shot': '跟踪镜头',
  'dolly shot': '推轨镜头', 'dolly zoom': '滑动变焦',
  'pan': '水平摇镜', 'panning': '水平摇镜',
  'tilt': '垂直摇镜', 'tilt up': '上摇', 'tilt down': '下摇',
  'zoom in': '推镜', 'zoom out': '拉镜',
  'handheld': '手持', 'steadicam': '稳定器',
  'split screen': '分屏', 'freeze frame': '定格',
  'b-roll': 'B-Roll素材', 'a-roll': '主镜头',
  'color grading': '调色', 'color correction': '校色',
  'bokeh': '虚化', 'depth of field': '景深', 'shallow dof': '浅景深',
  'lens flare': '镜头光晕', 'motion blur': '运动模糊',
  'fade in': '淡入', 'fade out': '淡出',
  'dissolve': '叠化', 'wipe': '划变',
  'j-cut': 'J剪辑', 'l-cut': 'L剪辑',
  'voiceover': '旁白', 'narration': '旁白',
  'cutaway': '切入镜头', 'insert shot': '插入镜头',
  'rack focus': '拉焦', 'pull focus': '拉焦',
  'over the shoulder': '过肩镜头', 'point of view': '主观镜头', 'pov': '主观镜头',
  'two shot': '双人镜头', 'reaction shot': '反应镜头',
  'crane shot': '摇臂镜头', 'jib shot': '摇臂镜头',
  'whip pan': '甩镜', 'dutch angle': '倾斜构图',
  'aspect ratio': '画幅比', 'letterbox': '宽银幕黑边',
  'keyframe': '关键帧', 'timeline': '时间线', 'sequence': '序列',
  'rough cut': '粗剪', 'fine cut': '精剪', 'final cut': '终剪',
  'trim': '修剪', 'splice': '拼接',

  // ── 补充: 活动/交流 ──
  'talking': '交谈', 'conversation': '对话', 'interview': '采访',
  'speaking': '演讲', 'presenting': '演示', 'exercising': '锻炼',
  'working': '工作', 'studying': '学习', 'playing': '玩耍',

  // ── 补充: 空间/房间 ──
  'room': '房间', 'living room': '客厅', 'bathroom': '浴室',
  'hallway': '走廊', 'studio': '工作室', 'warehouse': '仓库',
  'lobby': '大厅', 'corridor': '走廊',

  // ── 补充: Vlog/内容类型 ──
  'vlog': 'Vlog', 'daily': '日常', 'routine': '日常', 'haul': '开箱',
  'unboxing': '开箱', 'tutorial': '教程', 'review': '评测',
  'challenge': '挑战', 'mukbang': '吃播', 'asmr': 'ASMR',
  'behind the scenes': '幕后花絮', 'bts': '幕后花絮',

  // ── 补充: 人物组合 ──
  'group': '群体', 'couple': '情侣', 'solo': '独自',
  'baby': '婴儿', 'elder': '长辈', 'teenager': '青少年',

  // ── 补充: 关键特征 ──
  'highlight': '高光', 'dynamic': '动感', 'static': '静态',
  'energetic/dynamic': '活力动感', 'energetic, dynamic': '活力动感',
  'broll': 'B-Roll素材',
  'scenic': '风光', 'closeup detail': '特写细节',

  // ── 补充: 工作流/模板标签 ──
  'material-first': '素材先行', 'template': '模板',
  'video': '视频', 'short_video': '短视频', 'story': '故事',

  // ── 补充: 语义分析常见分类键 ──
  'activity': '活动', 'general': '综合', 'personal': '个人',
  'intimate': '亲密', 'intimate, personal': '亲密个人',
  'professional': '专业', 'casual': '休闲', 'formal': '正式',
  'abstract': '抽象', 'concrete': '具象', 'specific': '特定',
  'detail': '细节', 'overview': '概览', 'summary': '摘要',
  'emotional': '情感', 'descriptive': '描述', 'narrative': '叙事',
  'action': '动作', 'motion': '运动', 'movement': '移动',
  'interaction': '互动', 'gesture': '手势',
  'scenic view': '风景', 'close up': '特写', 'wide view': '全景',
}

// 合并映射：相似概念指向同一个规范词
const mergeMap = {
  '食物': '美食', '菜': '美食', '餐': '美食',
  '树木': '树', '树林': '森林',
  '大海': '海洋',
  '旅行者': '旅行',
}

/**
 * 翻译一个标签（英文→中文，已是中文则直接返回）
 */
export function translateTag(tag) {
  if (!tag) return ''
  const text = `${tag}`.trim().toLowerCase()
  if (!text) return ''
  // 中文字符检测
  if (/[\u4e00-\u9fa5]/.test(text)) return text
  // 直接匹配
  if (translationMap[text]) return translationMap[text]
  // 逗号分隔的复合值（如 "intimate, personal"）
  if (text.includes(',')) {
    const parts = text.split(',').map(p => {
      const trimmed = p.trim()
      return translationMap[trimmed] || trimmed
    })
    const translated = parts.filter(p => /[\u4e00-\u9fa5]/.test(p)).length
    if (translated >= parts.length / 2) return parts.join('')
  }
  // 去掉尾部 s/es/ing 后重试
  const stem = text.replace(/(?:ing|es|s)$/, '')
  if (stem !== text && translationMap[stem]) return translationMap[stem]
  // 下划线/连字符分隔 → 空格形式重试
  const spaced = text.replace(/[-_]/g, ' ')
  if (spaced !== text && translationMap[spaced]) return translationMap[spaced]
  // 多词标签：逐词翻译拼接
  const words = spaced.split(/\s+/)
  if (words.length > 1) {
    const parts = words.map(w => translationMap[w] || w)
    // 只有至少一半词被翻译了才拼接，否则保留原文
    const translated = parts.filter(p => /[\u4e00-\u9fa5]/.test(p)).length
    if (translated >= words.length / 2) return parts.join('')
  }
  return tag
}

/**
 * 翻译 + 去重合并
 */
export function translateAndDedupe(tags) {
  if (!Array.isArray(tags)) return []
  const seen = new Set()
  const result = []
  for (const tag of tags) {
    let translated = translateTag(tag)
    // 检查合并映射
    if (mergeMap[translated]) {
      translated = mergeMap[translated]
    }
    if (!seen.has(translated)) {
      seen.add(translated)
      result.push(translated)
    }
  }
  return result
}

export function useSemanticTranslation() {
  return { translateTag, translateAndDedupe }
}
