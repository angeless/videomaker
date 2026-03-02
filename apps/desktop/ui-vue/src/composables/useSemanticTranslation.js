/**
 * 语义标签翻译 + 去重映射
 * 解决反馈 #6：英文标签需翻译，相似词（如"美食"和"食物"）需合并
 */

const translationMap = {
  // ── 场景 ──
  'landscape': '风景', 'scenery': '风景', 'nature': '自然',
  'urban': '城市', 'city': '城市', 'cityscape': '城市', 'skyline': '天际线',
  'indoor': '室内', 'outdoor': '户外', 'interior': '室内', 'exterior': '户外',
  'beach': '海滩', 'ocean': '海洋', 'sea': '大海',
  'mountain': '山', 'mountains': '山', 'hill': '山丘',
  'forest': '森林', 'tree': '树', 'trees': '树木', 'woods': '树林',
  'river': '河流', 'lake': '湖泊', 'water': '水面', 'waterfall': '瀑布',
  'garden': '花园', 'park': '公园', 'field': '田野',
  'sunset': '日落', 'sunrise': '日出', 'dawn': '黎明', 'dusk': '黄昏',
  'night': '夜景', 'sky': '天空', 'cloud': '云', 'clouds': '云',
  'snow': '雪', 'rain': '雨', 'fog': '雾',
  'street': '街道', 'road': '公路', 'highway': '高速公路', 'path': '小路',
  'building': '建筑', 'architecture': '建筑', 'bridge': '桥',
  'temple': '寺庙', 'church': '教堂', 'castle': '城堡',

  // ── 人物 / 活动 ──
  'person': '人物', 'people': '人群', 'crowd': '人群',
  'man': '男性', 'woman': '女性', 'child': '儿童', 'children': '儿童',
  'face': '人脸', 'portrait': '肖像', 'selfie': '自拍',
  'walking': '行走', 'running': '跑步', 'sitting': '坐',
  'dancing': '跳舞', 'singing': '唱歌', 'cooking': '烹饪',
  'eating': '用餐', 'drinking': '饮', 'shopping': '购物',
  'travel': '旅行', 'traveling': '旅行', 'traveler': '旅行者',
  'swimming': '游泳', 'driving': '驾驶', 'cycling': '骑行',

  // ── 美食 ──
  'food': '美食', 'cuisine': '美食', 'meal': '餐食', 'dish': '菜品',
  'restaurant': '餐厅', 'cafe': '咖啡店', 'coffee': '咖啡',
  'fruit': '水果', 'vegetable': '蔬菜', 'meat': '肉',
  'dessert': '甜点', 'cake': '蛋糕', 'bread': '面包',

  // ── 动物 ──
  'animal': '动物', 'dog': '狗', 'cat': '猫', 'bird': '鸟',
  'fish': '鱼', 'horse': '马', 'pet': '宠物',

  // ── 物品 ──
  'car': '汽车', 'vehicle': '车辆', 'boat': '船', 'airplane': '飞机',
  'phone': '手机', 'computer': '电脑', 'camera': '相机',
  'book': '书', 'flower': '花', 'flowers': '花',
  'furniture': '家具', 'table': '桌子', 'chair': '椅子',
  'clothing': '服装', 'fashion': '时尚',

  // ── 风格 / 属性 ──
  'beautiful': '美丽', 'colorful': '色彩丰富', 'vibrant': '鲜艳',
  'dark': '暗', 'bright': '明亮', 'warm': '温暖', 'cool': '清凉',
  'vintage': '复古', 'modern': '现代', 'traditional': '传统',
  'luxury': '奢华', 'simple': '简约', 'elegant': '优雅',
  'aesthetic': '美学', 'artistic': '艺术',
  'romantic': '浪漫', 'dramatic': '戏剧性', 'peaceful': '宁静',
  'happy': '快乐', 'sad': '忧伤', 'funny': '有趣',
}

// 合并映射：相似概念指向同一个规范词
const mergeMap = {
  '食物': '美食',
  '菜': '美食',
  '餐': '美食',
  '树木': '树',
  '树林': '森林',
  '人群': '人物',
  '大海': '海洋',
  '室内': '室内',
  '户外': '户外',
  '行走': '行走',
  '城市': '城市',
  '风景': '风景',
  '建筑': '建筑',
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
  return translationMap[text] || tag
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
