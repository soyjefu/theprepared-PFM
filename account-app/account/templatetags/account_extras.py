from django import template

register = template.Library()

@register.filter(name='get_obj_attr')
def get_obj_attr(obj, attr_name):
    """커스텀 getattr 필터: 객체의 속성을 동적으로 가져옵니다."""
    try:
        return getattr(obj, attr_name)
    except (AttributeError, TypeError):
        return None
